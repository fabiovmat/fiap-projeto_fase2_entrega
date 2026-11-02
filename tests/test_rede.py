"""Validação da tradução: a rede não pode ser presumida pela numeração."""
import pytest
from alfabetizacao.rede import normalizar_rotulo, categoria_rede, resolver_codigo_rede


def test_normalizacao_descricao():
    assert normalizar_rotulo(' PÚBLICA ') == 'publica'
    assert categoria_rede('Rede Municipal') == 'municipal'
    assert categoria_rede('Pública') == 'publica'
    assert categoria_rede('Estadual') is None


def test_resolver_por_dicionario_e_por_tabela():
    linhas = [
        dict(id_tabela='municipio', chave='3', valor='Municipal'),
        dict(id_tabela='municipio', chave='5', valor='Pública'),
        dict(id_tabela='uf', chave='5', valor='Pública'),
    ]
    assert resolver_codigo_rede(linhas, 'municipio', 'municipal', ['0', '2', '3', '5']) == '3'
    assert resolver_codigo_rede(linhas, 'uf', 'publica', ['2', '3', '5']) == '5'


def test_nao_inventa_codigo_sem_dicionario():
    with pytest.raises(ValueError, match='Não foi possível'):
        resolver_codigo_rede([], 'municipio', 'municipal', ['3'])


def test_municipio_nao_exige_categoria_publica(monkeypatch):
    """Mesmo sem código público em município, pode processar comparação municipal."""
    from alfabetizacao import rede
    class FakeCloud:
        class Settings:
            def table(self, layer, name):
                return f"`projeto.{layer}.{name}`"
        s = Settings()
        def rows(self, query, label):
            if label == 'quality-dicionario-rede':
                return [dict(id_tabela='municipio', chave='3', valor='Municipal'),
                        dict(id_tabela='uf', chave='5', valor='Pública')]
            if label == 'quality-redes-municipio':
                return [dict(codigo='2'), dict(codigo='3'), dict(codigo='5')]
            if label == 'quality-redes-uf':
                return [dict(codigo='5'), dict(codigo='2')]
            raise AssertionError(label)
    got = rede.obter_codigos_oficiais(FakeCloud())
    assert got == {('municipio', 'municipal'): '3', ('uf', 'publica'): '5'}
    assert ('municipio', 'publica') not in got


def test_join_separacao_por_rede():
    from pathlib import Path
    source = (Path(__file__).parents[1] / 'src/alfabetizacao/gold.py').read_text()
    assert 'public_uf = f"SELECT * FROM' in source
    assert "'meta_uf_publica'" in source
    assert 'codigo_publica_municipio' not in source
    assert 'meta_uf_2030_percentual' not in source


def test_descricoes_reais_do_dicionario():
    """Códigos 5 e 6 possuem abrangências distintas no dicionário oficial."""
    assert categoria_rede('Pública (Estadual e Municipal)') == 'publica'
    assert categoria_rede('PÚBLICA (  ESTADUAL E MUNICIPAL )') == 'publica'
    assert categoria_rede('Pública (Federal, Estadual e Municipal)') is None
    assert categoria_rede('Total (Federal, Estadual, Municipal e Privada)') is None


def test_resolver_rede_publica_usa_codigo_5_mesmo_com_6_presente():
    linhas = [
        dict(id_tabela='uf', chave='3', valor='Municipal'),
        dict(id_tabela='uf', chave='5', valor='Pública (Estadual e Municipal)'),
        dict(id_tabela='uf', chave='6', valor='Pública (Federal, Estadual e Municipal)'),
    ]
    assert resolver_codigo_rede(linhas, 'uf', 'publica', ['0', '2', '3', '5', '6']) == '5'


def test_nao_usa_mapeamento_de_outra_tabela():
    linhas = [dict(id_tabela='municipio', chave='5', valor='Pública (Estadual e Municipal)')]
    with pytest.raises(ValueError, match='Não foi possível'):
        resolver_codigo_rede(linhas, 'uf', 'publica', ['5'])


def test_obter_codigos_reais_em_cloud_simulado():
    """Teste do fluxo de obtenção com os códigos observados no GCP."""
    from alfabetizacao.rede import obter_codigos_oficiais

    class CloudFalso:
        class Config:
            @staticmethod
            def table(layer, name):
                return f'`exemplo.{layer}.{name}`'
        s = Config()

        def rows(self, sql, label):
            if label == 'quality-dicionario-rede':
                return [
                    dict(id_tabela='municipio', chave='3', valor='Municipal'),
                    dict(id_tabela='municipio', chave='5', valor='Pública (Estadual e Municipal)'),
                    dict(id_tabela='uf', chave='3', valor='Municipal'),
                    dict(id_tabela='uf', chave='5', valor='Pública (Estadual e Municipal)'),
                ]
            if label == 'quality-redes-municipio':
                return [dict(codigo=v) for v in ('0', '2', '3', '5')]
            if label == 'quality-redes-uf':
                return [dict(codigo=v) for v in ('0', '2', '3', '5')]
            raise AssertionError(label)

    assert obter_codigos_oficiais(CloudFalso()) == {
        ('municipio', 'municipal'): '3',
        ('uf', 'publica'): '5',
    }
