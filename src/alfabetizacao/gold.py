"""Qualidade bloqueante + Gold com lineage das seis entidades oficiais."""
from .cloud import Cloud
from .quality import QualityError
from .schema import pick, numeric_field, planned_meta_year_columns
from .rede import obter_codigos_oficiais

UF_BY_IBGE = {
    "11":"RO", "12":"AC", "13":"AM", "14":"RR", "15":"PA", "16":"AP", "17":"TO",
    "21":"MA", "22":"PI", "23":"CE", "24":"RN", "25":"PB", "26":"PE", "27":"AL",
    "28":"SE", "29":"BA", "31":"MG", "32":"ES", "33":"RJ", "35":"SP",
    "41":"PR", "42":"SC", "43":"RS", "50":"MS", "51":"MT", "52":"GO", "53":"DF",
}


def municipal_base_expr(cloud: Cloud):
    cols = cloud.columns("silver", "municipio")
    if "_id_municipio" not in cols:
        raise ValueError("municipio sem id_municipio: verifique o esquema e o mapeamento")
    if "_sigla_uf" in cols:
        ufexpr = "_sigla_uf"
    else:
        parts = " ".join(f"WHEN '{code}' THEN '{uf}'" for code, uf in UF_BY_IBGE.items())
        ufexpr = f"CASE SUBSTR(_id_municipio,1,2) {parts} ELSE NULL END"
    return f"SELECT *, {ufexpr} AS _uf_join FROM {cloud.s.table('silver','municipio')}"


def keys_for(left, right, *, required):
    common = [col for col in ("_id_municipio", "_sigla_uf", "_ano", "_rede", "_serie") if col in left and col in right]
    for needed in required:
        if needed not in common:
            raise ValueError(f"Join sem chave obrigatória {needed}; interseção={common}; esquerda={left}; direita={right}")
    return common


def match_check(cloud: Cloud, run_id, label, left_sql, right_table, join_keys, threshold, *, right_where="", kind="BLOQUEANTE"):
    """Valida correspondência no universo de comparação aplicável."""
    expr = " AND ".join(f"CAST(l.{k} AS STRING)=CAST(r.{k} AS STRING)" for k in join_keys)
    right = cloud.s.table("silver", right_table)
    keys = ",".join(join_keys)
    sql = f"""WITH l AS ({left_sql}), r AS (
       SELECT DISTINCT {keys}, 1 AS encontrou FROM {right} {right_where}
    ) SELECT COUNT(*) AS total, COUNTIF(r.encontrou IS NOT NULL) AS casados
    FROM l LEFT JOIN r ON {expr}"""
    row = cloud.rows(sql, f"quality-match-{label}")[0]
    total, matched = row["total"], row["casados"]
    rate = (matched / total) if total else 0.0
    cloud.quality(run_id, "join_" + label, kind, rate, threshold, total > 0 and rate >= threshold,
                  f"{matched}/{total}; chaves={join_keys}; taxa mínima {threshold:.1%}; "
                  f"universo={'total histórico' if kind == 'INFORMATIVA' else 'recorte aplicável'}")
    return rate


def alunos_recorte_individual_sql(cloud: Cloud, left_sql: str) -> str:
    """Seleciona apenas redes individuais definidas no dicionário de alunos.

    Redes 0 (Total) e 5 (Pública Estadual+Municipal) são agregados e não
    podem ser associadas diretamente por igualdade a microdados individuais.
    O ano/série deve existir na fonte, independentemente da rede, para que
    a ausência de uma rede individual não fique escondida no denominador.
    """
    alunos = cloud.s.table('silver', 'alunos_resumo')
    dic = cloud.s.table('silver', 'dicionario')
    return (f"SELECT m.* FROM ({left_sql}) AS m "
            f"WHERE EXISTS (SELECT 1 FROM {dic} AS d "
            f"WHERE LOWER(TRIM(d.id_tabela)) = 'alunos' "
            f"AND LOWER(TRIM(d.nome_coluna)) = 'rede' "
            f"AND TRIM(CAST(d.chave AS STRING)) = m._rede) "
            f"AND EXISTS (SELECT 1 FROM {alunos} AS a "
            f"WHERE a._ano = m._ano AND a._serie = m._serie)")


def alunos_grupos_check(cloud: Cloud, run_id: str, left_sql: str, threshold: float):
    """Bloqueia falhas em qualquer combinação de ano, rede e série elegível."""
    alunos = cloud.s.table('silver', 'alunos_resumo')
    sql = f"""WITH m AS ({left_sql}),
        a AS (SELECT DISTINCT _id_municipio, _ano, _rede, _serie FROM {alunos})
        SELECT m._ano AS ano, m._rede AS rede, m._serie AS serie,
               COUNT(*) AS total,
               COUNTIF(a._id_municipio IS NOT NULL) AS casados
        FROM m LEFT JOIN a
          ON m._id_municipio = a._id_municipio
         AND m._ano = a._ano AND m._rede = a._rede AND m._serie = a._serie
        GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"""
    grupos = cloud.rows(sql, 'quality-alunos-segmentos')
    if not grupos:
        cloud.quality(run_id, 'join_alunos_segmentos_vazios', 'BLOQUEANTE',
                      0.0, threshold, False,
                      'Nenhum segmento individual elegível; verifique o dicionário e as fontes')
    for row in grupos:
        total = row['total']
        casados = row['casados']
        rate = casados / total if total else 0.0
        label = f"join_alunos_ano_{row['ano']}_rede_{row['rede']}_serie_{row['serie']}"
        cloud.quality(run_id, label, 'BLOQUEANTE', rate, threshold,
                      total > 0 and rate >= threshold,
                      f"{casados}/{total}; recorte individual ano={row['ano']}, "
                      f"rede={row['rede']}, serie={row['serie']}")


def uniqueness_check(cloud: Cloud, run_id, table, keys, *, where=""):
    key_sql = ", ".join(keys)
    sql = f"""SELECT COUNT(*) AS duplicados FROM (
       SELECT {key_sql}, COUNT(*) AS qtd FROM {cloud.s.table('silver',table)} {where}
       GROUP BY {key_sql} HAVING COUNT(*) > 1
    )"""
    count = cloud.rows(sql, "quality-unique-" + table)[0]["duplicados"]
    cloud.quality(run_id, "duplicidade_" + table, "BLOQUEANTE", count, 0, count == 0,
                  "Grão avaliado: " + key_sql)


def null_check(cloud: Cloud, run_id, table, col):
    num = cloud.rows(
        f"SELECT COUNTIF({col} IS NULL) AS quantidade FROM {cloud.s.table('silver',table)}",
        "quality-null-" + table
    )[0]["quantidade"]
    cloud.quality(run_id, "nulos_" + table + col, "BLOQUEANTE", num, 0, num == 0)


def student_group_sql(cloud: Cloud):
    cols = cloud.columns("silver", "alunos")
    if "_id_municipio" not in cols:
        raise ValueError("alunos sem id_municipio: precisa de chave verificável para relação territorial")
    keys = [x for x in ("_id_municipio", "_ano", "_rede", "_serie") if x in cols]
    fields = ", ".join(keys)
    return f"""SELECT {fields}, COUNT(*) AS total_registros_alunos,
       'oficial_microdado' AS origem_alunos
       FROM {cloud.s.table('silver','alunos')}
       GROUP BY {fields}""", keys


def validate_and_publish(cloud: Cloud, run_id: str):
    s = cloud.s
    cols = {name: set(cloud.columns("silver", name)) for name in (
        "municipio", "meta_alfabetizacao_municipio", "uf", "meta_alfabetizacao_uf",
        "meta_alfabetizacao_brasil", "alunos", "dicionario")}
    indicator_m = pick(cols["municipio"], "indicador", required=True)
    indicator_uf = pick(cols["uf"], "indicador", required=True)
    for table, key in (("municipio", "_id_municipio"), ("meta_alfabetizacao_municipio", "_id_municipio"),
                       ("uf", "_sigla_uf"), ("meta_alfabetizacao_uf", "_sigla_uf")):
        if key not in cols[table]:
            raise ValueError(f"{table} não possui {key}: confira docs/esquema.json")
        null_check(cloud, run_id, table, key)
    # Percentuais válidos: 0..100; valor ausente não é convertido em zero.
    for t, c in (("municipio", indicator_m), ("uf", indicator_uf)):
        bad = cloud.rows(
            f"SELECT COUNTIF(SAFE_CAST(`{c}` AS FLOAT64) NOT BETWEEN 0 AND 100) AS falhas "
            f"FROM {s.table('silver',t)}", f"quality-range-{t}") [0]["falhas"]
        cloud.quality(run_id, "faixa_percentual_" + t, "BLOQUEANTE", bad, 0, bad == 0)
    base = municipal_base_expr(cloud)
    base_cols = cols["municipio"] | {"_uf_join"}
    # Os códigos numéricos são validados contra o dicionário oficial, nunca presumidos.
    codes = obter_codigos_oficiais(cloud)
    codigo_municipal = codes[("municipio", "municipal")].replace("'", "''")
    codigo_publica_uf = codes[("uf", "publica")].replace("'", "''")
    # Etapa 1: agrega alunos; remove granularidade individual somente para publicação Gold.
    alunos_sql, alunos_keys = student_group_sql(cloud)
    cloud.step(run_id, "silver-alunos-resumo", lambda: cloud.query(
        f"CREATE OR REPLACE TABLE {s.table('silver','alunos_resumo')} AS {alunos_sql}", "silver-alunos-resumo"
    ))
    # Usa rótulo _sigla_uf consistente entre municipio e UF.
    prepared = f"SELECT b.* EXCEPT(_uf_join), b._uf_join AS _sigla_uf_gold FROM ({base}) b"
    prep_cols = base_cols | {"_sigla_uf_gold"}
    right_defs = [
        ("meta_municipio", "meta_alfabetizacao_municipio", ["_id_municipio"]),
        ("alunos", "alunos_resumo", ["_id_municipio"]),
        ("indicador_uf", "uf", ["_sigla_uf"]),
    ]
    for label, right, required in right_defs:
        right_cols = cols[right] if right in cols else set(cloud.columns("silver", right))
        # _sigla_uf_gold é apenas uma coluna auxiliar do lado esquerdo.
        left_cols = set(prep_cols)
        if "_sigla_uf_gold" in left_cols:
            left_cols.add("_sigla_uf")
        common = keys_for(left_cols, right_cols, required=required)
        if "_sigla_uf" in common:
            sql_base = f"SELECT *, _sigla_uf_gold AS _sigla_uf FROM ({prepared})"
            # Evita colisão caso a fonte também traga _sigla_uf.
            if "_sigla_uf" in cols["municipio"]:
                sql_base = f"SELECT * REPLACE(_sigla_uf_gold AS _sigla_uf) FROM ({prepared})"
        else:
            sql_base = prepared
        # Se a esquerda já tem _sigla_uf, não precisa do apelido auxiliar.
        if "_sigla_uf" in cols["municipio"] and "_sigla_uf" in common:
            sql_base = f"SELECT * FROM ({base})"
        # Metas são metas de um recorte específico, não de todas as redes.
        # Filtramos o universo factual, e conferimos a rede na fonte de metas.
        right_where = ""
        if label == "meta_municipio":
            common.remove("_rede")
            sql_base = f"SELECT * FROM ({sql_base}) WHERE _rede = '{codigo_municipal}'"
            right_where = "WHERE LOWER(TRIM(_rede)) = 'municipal'"
        if label == "alunos":
            # Cobertura de todos os recortes, inclusive redes agregadas:
            # mantém 51,71% como indicador histórico INFORMATIVO.
            match_check(cloud, run_id, "alunos_cobertura_historica", sql_base,
                        right, common, s.match_threshold, kind="INFORMATIVA")
            # A fonte de alunos não possui chaves 0/5 das redes agregadas.
            # As redes individuais vêm do dicionário oficial, não de um palpite.
            sql_base = alunos_recorte_individual_sql(cloud, sql_base)
            match_check(cloud, run_id, "alunos_redes_individuais", sql_base,
                        right, common, s.match_threshold)
            # Evita esconder um segmento ruim numa boa média geral.
            alunos_grupos_check(cloud, run_id, sql_base, s.match_threshold)
        else:
            match_check(cloud, run_id, label, sql_base, right, common, s.match_threshold,
                        right_where=right_where)
        if right != "alunos_resumo":
            uniqueness_check(cloud, run_id, right, common, where=right_where)
    # A meta por UF tem recorte Público; seu universo de qualidade é silver.uf,
    # não silver.municipio. Jamais exigimos ou inferimos rede pública no município.
    public_uf = f"SELECT * FROM {s.table('silver','uf')} WHERE _rede = '{codigo_publica_uf}'"
    match_check(cloud, run_id, 'meta_uf_publica', public_uf,
                'meta_alfabetizacao_uf', ['_sigla_uf', '_ano'], s.match_threshold,
                right_where="WHERE LOWER(TRIM(_rede)) IN ('pública','publica')")
    uniqueness_check(cloud, run_id, 'meta_alfabetizacao_uf', ['_sigla_uf', '_ano'],
                     where="WHERE LOWER(TRIM(_rede)) IN ('pública','publica')")
    # A chave composta também precisa ser única na entidade factual.
    unique_base = [x for x in ("_id_municipio", "_ano", "_rede", "_serie") if x in cols["municipio"]]
    uniqueness_check(cloud, run_id, "municipio", unique_base)
    for name in ("municipio", "uf"):
        if "_ano" in cols[name]:
            null_check(cloud, run_id, name, "_ano")
    # Regras bloqueantes terminaram com sucesso. Daqui em diante publicamos Gold.
    if "meta_alfabetizacao_2030" not in cols["meta_alfabetizacao_uf"]:
        raise ValueError("meta_alfabetizacao_uf sem meta_alfabetizacao_2030")
    cloud.step(run_id, "gold-alunos-resumo", lambda: cloud.query(
        f"CREATE OR REPLACE TABLE {s.table('gold','alunos_resumo')} AS "
        f"SELECT * FROM {s.table('silver','alunos_resumo')}", "gold-alunos-resumo"
    ))
    meta_cols = cols["meta_alfabetizacao_municipio"]
    meta_2030 = numeric_field(meta_cols, "meta_alfabetizacao_2030")
    if "meta_alfabetizacao_2030" not in meta_cols:
        raise ValueError("meta_alfabetizacao_municipio sem meta_alfabetizacao_2030")
    if "_sigla_uf" in cols["municipio"]:
        base_uf_expr = "m._sigla_uf"
    else:
        parts = " ".join(f"WHEN '{code}' THEN '{uf}'" for code, uf in UF_BY_IBGE.items())
        base_uf_expr = f"CASE SUBSTR(m._id_municipio,1,2) {parts} ELSE NULL END"
    joins = []
    targets = (
        ("mm", "meta_alfabetizacao_municipio", ["_id_municipio"]),
        ("a", "alunos_resumo", ["_id_municipio"]),
        ("u", "uf", ["_sigla_uf"]),
    )
    for alias, name, req in targets:
        right = cols[name] if name in cols else set(cloud.columns("silver", name))
        left = set(cols["municipio"]) | {"_sigla_uf"}
        common = keys_for(left, right, required=req)
        if name in ("meta_alfabetizacao_municipio", "meta_alfabetizacao_uf"):
            common.remove("_rede")  # Rede é validada explicitamente nos recortes abaixo.
        predicates = [
            f"CAST(({base_uf_expr}) AS STRING)=CAST({alias}._sigla_uf AS STRING)" if k == "_sigla_uf"
            else f"CAST(m.{k} AS STRING)=CAST({alias}.{k} AS STRING)"
            for k in common
        ]
        if name == "meta_alfabetizacao_municipio":
            predicates += [f"m._rede = '{codigo_municipal}'", "LOWER(TRIM(mm._rede)) = 'municipal'"]
        layer = "gold" if name == "alunos_resumo" else "silver"
        joins.append(f"LEFT JOIN {s.table(layer,name)} {alias} ON " + " AND ".join(predicates))
    rate = f"SAFE_CAST(m.`{indicator_m}` AS FLOAT64)"
    year_metas = planned_meta_year_columns(meta_cols)
    if "_ano" in cols["municipio"]:
        year_case = "CASE m._ano " + " ".join(
            f"WHEN {year} THEN SAFE_CAST(mm.`{col}` AS FLOAT64)" for year, col in sorted(year_metas.items())
        ) + " ELSE NULL END" if year_metas else "CAST(NULL AS FLOAT64)"
    else:
        year_case = "CAST(NULL AS FLOAT64)"
    sql_mun = f"""CREATE OR REPLACE TABLE {s.table('gold','indicador_municipio')} AS
    SELECT m._id_municipio AS id_municipio, {base_uf_expr} AS sigla_uf,
           {('m._ano' if '_ano' in cols['municipio'] else 'CAST(NULL AS INT64)')} AS ano,
           {('m._rede' if '_rede' in cols['municipio'] else 'CAST(NULL AS STRING)')} AS rede_codigo,
           {('m._serie' if '_serie' in cols['municipio'] else 'CAST(NULL AS STRING)')} AS serie_codigo,
           {rate} AS indicador_oficial_percentual,
           {year_case} AS meta_pactuada_ano_percentual,
           SAFE_CAST(mm.meta_alfabetizacao_2030 AS FLOAT64) AS meta_pactuada_2030_percentual,
           SAFE_CAST(mm.meta_alfabetizacao_2030 AS FLOAT64) - {rate} AS distancia_pactuada_2030_pp,
           CASE WHEN mm.meta_alfabetizacao_2030 IS NULL OR {rate} IS NULL THEN 'sem_dado'
                WHEN {rate} >= SAFE_CAST(mm.meta_alfabetizacao_2030 AS FLOAT64) THEN 'atingiu'
                ELSE 'nao_atingiu' END AS status_meta_2030,
           SAFE_CAST(u.`{indicator_uf}` AS FLOAT64) AS indicador_uf_oficial_percentual,
           a.total_registros_alunos,
           'oficial' AS origem_indicador
    FROM {s.table('silver','municipio')} m
    {' '.join(joins)}"""
    cloud.step(run_id, "gold-indicador-municipio", lambda: cloud.query(sql_mun, "gold-municipio"))
    keys_uf = keys_for(cols["uf"], cols["meta_alfabetizacao_uf"], required=["_sigla_uf"])
    keys_uf.remove("_rede")
    on_uf = " AND ".join(f"CAST(u.{k} AS STRING)=CAST(mu.{k} AS STRING)" for k in keys_uf)
    on_uf += f" AND u._rede = '{codigo_publica_uf}' AND LOWER(TRIM(mu._rede)) IN ('pública', 'publica')"
    cloud.step(run_id, "gold-indicador-uf", lambda: cloud.query(
        f"""CREATE OR REPLACE TABLE {s.table('gold','indicador_uf')} AS
        SELECT u.*, SAFE_CAST(mu.meta_alfabetizacao_2030 AS FLOAT64) AS meta_pactuada_2030
        FROM {s.table('silver','uf')} u LEFT JOIN {s.table('silver','meta_alfabetizacao_uf')} mu ON {on_uf}""",
        "gold-uf"
    ))
    cloud.step(run_id, "gold-metas-brasil", lambda: cloud.query(
        f"CREATE OR REPLACE TABLE {s.table('gold','metas_brasil')} AS SELECT * FROM {s.table('silver','meta_alfabetizacao_brasil')}",
        "gold-brasil"))
    # Dicionário oficial materializado na Gold para interpretação verificável de códigos.
    cloud.step(run_id, "gold-dicionario", lambda: cloud.query(
        f"CREATE OR REPLACE TABLE {s.table('gold','dicionario')} AS SELECT * FROM {s.table('silver','dicionario')}",
        "gold-dicionario"))
