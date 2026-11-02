"""Testes de compatibilidade entre redes individuais e agregadas."""
import pytest
from alfabetizacao.gold import alunos_recorte_individual_sql, alunos_grupos_check, match_check
from alfabetizacao.quality import QualityError


class FakeSettings:
    @staticmethod
    def table(layer, name):
        return f"`projeto.{layer}.{name}`"


class FakeCloud:
    s = FakeSettings()

    def __init__(self, total=13131, matched=12408, grupos=None):
        self.total = total
        self.matched = matched
        self.grupos = grupos or []
        self.validacoes = []
        self.sql = ''

    def rows(self, sql, label):
        self.sql = sql
        if label == 'quality-alunos-segmentos':
            return self.grupos
        return [{'total': self.total, 'casados': self.matched}]

    def quality(self, run_id, name, kind, rate, threshold, passed, details=''):
        self.validacoes.append((name, kind, rate, threshold, passed, details))
        if kind == 'BLOQUEANTE' and not passed:
            raise QualityError(name)


def test_recorte_usa_dicionario_individual_e_ano_serie():
    sql = alunos_recorte_individual_sql(FakeCloud(), 'SELECT * FROM `projeto.silver.municipio`')
    assert "d.id_tabela)) = 'alunos'" in sql
    assert "d.nome_coluna)) = 'rede'" in sql
    assert 'TRIM(CAST(d.chave AS STRING)) = m._rede' in sql
    assert 'a._ano = m._ano AND a._serie = m._serie' in sql
    assert 'a._rede = m._rede' not in sql  # rede individual ausente deve falhar, não ser ignorada
    assert '5' not in sql and '0' not in sql  # não inventa códigos, consulta dicionário


def test_match_individual_94_49_porcento_aprova():
    cloud = FakeCloud()
    match_check(cloud, 'run', 'alunos_redes_individuais', 'SELECT * FROM X', 'alunos_resumo',
                ['_id_municipio', '_ano', '_rede', '_serie'], .8)
    assert cloud.validacoes[-1][4] is True
    assert cloud.validacoes[-1][2] == pytest.approx(12408/13131)


def test_cobertura_historica_51_71_apenas_informativa():
    cloud = FakeCloud(23995, 12408)
    match_check(cloud, 'run', 'alunos_cobertura_historica', 'SELECT * FROM X', 'alunos_resumo',
                ['_id_municipio', '_ano', '_rede', '_serie'], .8, kind='INFORMATIVA')
    assert cloud.validacoes[-1][1] == 'INFORMATIVA'
    assert cloud.validacoes[-1][4] is False


def test_segmentos_reais_passam():
    rows = [
        {'ano': 2023, 'rede': '2', 'serie': '2', 'total': 1149, 'casados': 1054},
        {'ano': 2023, 'rede': '3', 'serie': '2', 'total': 5448, 'casados': 4821},
        {'ano': 2024, 'rede': '2', 'serie': '2', 'total': 1086, 'casados': 1085},
        {'ano': 2024, 'rede': '3', 'serie': '2', 'total': 5448, 'casados': 5448},
    ]
    cloud = FakeCloud(grupos=rows)
    alunos_grupos_check(cloud, 'run', 'SELECT * FROM X', .8)
    assert len(cloud.validacoes) == 4
    assert all(v[4] for v in cloud.validacoes)
    assert '_serie' in cloud.sql


def test_segmento_abaixo_80_bloqueia_mesmo_com_media_global_boa():
    cloud = FakeCloud(grupos=[{'ano': 2023, 'rede': '3', 'serie': '2', 'total': 100, 'casados': 70}])
    with pytest.raises(QualityError, match='join_alunos_ano_2023_rede_3_serie_2'):
        alunos_grupos_check(cloud, 'run', 'SELECT * FROM X', .8)


def test_ausencia_total_de_segmentos_bloqueia():
    with pytest.raises(QualityError, match='join_alunos_segmentos_vazios'):
        alunos_grupos_check(FakeCloud(), 'run', 'SELECT * FROM X', .8)


def test_sem_linhas_no_recorte_bloqueia():
    with pytest.raises(QualityError):
        match_check(FakeCloud(0, 0), 'run', 'alunos_redes_individuais', 'SELECT * FROM X',
                    'alunos_resumo', ['_id_municipio', '_ano', '_rede', '_serie'], .8)
