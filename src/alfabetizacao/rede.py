"""Compatibilização de redes educacionais a partir do dicionário oficial.

Evita inferir que código 3 ou 5 significa uma categoria sem confirmar a fonte.
"""
import re
import unicodedata


def normalizar_rotulo(texto):
    sem_acentos = ''.join(c for c in unicodedata.normalize('NFKD', str(texto))
                           if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', sem_acentos.strip().lower())


def categoria_rede(texto):
    nome = normalizar_rotulo(texto)
    if nome in ('municipal', 'rede municipal'):
        return 'municipal'
    # A fonte oficial distingue "Pública (Estadual e Municipal)" (código 5)
    # de "Pública (Federal, Estadual e Municipal)" (código 6).
    # São universos diferentes: só aceitamos o primeiro nas metas deste pipeline.
    if nome in ('publica', 'rede publica'):
        return 'publica'
    if re.fullmatch(r'(?:rede )?publica\s*\(\s*estadual e municipal\s*\)', nome):
        return 'publica'
    return None


def resolver_codigo_rede(linhas_dicionario, tabela, categoria, codigos_presentes):
    """Exige correspondência não ambígua no dicionário e nos dados realmente observados."""
    presentes = {str(x).strip() for x in codigos_presentes if x is not None}
    escolhidos = set()
    for linha in linhas_dicionario:
        chave = str(linha['chave']).strip()
        if chave not in presentes or categoria_rede(linha['valor']) != categoria:
            continue
        id_tabela = normalizar_rotulo(linha['id_tabela'])
        tabelas = re.split(r'[,;\s/]+', id_tabela)
        # Não usar o código de outra tabela como substituto silencioso.
        # O dicionário oficial oferece entradas específicas para uf e municipio.
        if tabela in tabelas or id_tabela.endswith('.' + tabela):
            escolhidos.add(chave)
    if len(escolhidos) != 1:
        raise ValueError(
            f"Não foi possível identificar unicamente a rede '{categoria}' em '{tabela}' "
            f"a partir de silver.dicionario. Candidatos={sorted(escolhidos)}, "
            f"códigos presentes={sorted(presentes)}. "
            "Consulte SELECT id_tabela, nome_coluna, chave, valor "
            "FROM silver.dicionario WHERE LOWER(nome_coluna)='rede'."
        )
    return next(iter(escolhidos))


def obter_codigos_oficiais(cloud):
    rows = cloud.rows(
        f"SELECT id_tabela, nome_coluna, CAST(chave AS STRING) AS chave, valor "
        f"FROM {cloud.s.table('silver','dicionario')} "
        f"WHERE LOWER(TRIM(nome_coluna)) = 'rede'",
        'quality-dicionario-rede',
    )
    result = {}
    for tabela in ('municipio', 'uf'):
        redes = cloud.rows(
            f"SELECT DISTINCT CAST(_rede AS STRING) AS codigo "
            f"FROM {cloud.s.table('silver', tabela)}",
            'quality-redes-' + tabela,
        )
        presentes = [row['codigo'] for row in redes]
        # Metas municipais são da rede Municipal. A rede Pública é comparação por UF.
        categorias = ('municipal',) if tabela == 'municipio' else ('publica',)
        for categoria in categorias:
            result[(tabela, categoria)] = resolver_codigo_rede(
                rows, tabela, categoria, presentes
            )
    return result
