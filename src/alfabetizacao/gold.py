"""Qualidade bloqueante + Gold com lineage das seis entidades oficiais."""
from .cloud import Cloud
from .quality import QualityError
from .schema import pick, numeric_field, planned_meta_year_columns

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


def match_check(cloud: Cloud, run_id, label, left_sql, right_table, join_keys, threshold):
    expr = " AND ".join(f"CAST(l.{k} AS STRING)=CAST(r.{k} AS STRING)" for k in join_keys)
    right = cloud.s.table("silver", right_table)
    keys = ",".join(join_keys)
    sql = f"""WITH l AS ({left_sql}), r AS (
       SELECT DISTINCT {keys}, 1 AS encontrou FROM {right}
    ) SELECT COUNT(*) AS total, COUNTIF(r.encontrou IS NOT NULL) AS casados
    FROM l LEFT JOIN r ON {expr}"""
    row = cloud.rows(sql, f"quality-match-{label}")[0]
    total, matched = row["total"], row["casados"]
    rate = (matched / total) if total else 0.0
    cloud.quality(run_id, "join_" + label, "BLOQUEANTE", rate, threshold, rate >= threshold,
                  f"{matched}/{total}; chaves={join_keys}; taxa mínima {threshold:.1%}")
    return rate


def uniqueness_check(cloud: Cloud, run_id, table, keys):
    key_sql = ", ".join(keys)
    sql = f"""SELECT COUNT(*) AS duplicados FROM (
       SELECT {key_sql}, COUNT(*) AS qtd FROM {cloud.s.table('silver',table)}
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
        ("meta_uf", "meta_alfabetizacao_uf", ["_sigla_uf"]),
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
        match_check(cloud, run_id, label, sql_base, right, common, s.match_threshold)
        if right != "alunos_resumo":
            uniqueness_check(cloud, run_id, right, common)
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
        ("mu", "meta_alfabetizacao_uf", ["_sigla_uf"]),
    )
    for alias, name, req in targets:
        right = cols[name] if name in cols else set(cloud.columns("silver", name))
        left = set(cols["municipio"]) | {"_sigla_uf"}
        common = keys_for(left, right, required=req)
        predicates = [
            f"CAST(({base_uf_expr}) AS STRING)=CAST({alias}._sigla_uf AS STRING)" if k == "_sigla_uf"
            else f"CAST(m.{k} AS STRING)=CAST({alias}.{k} AS STRING)"
            for k in common
        ]
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
           {numeric_field(cols['meta_alfabetizacao_uf'],'meta_alfabetizacao_2030').replace('`meta_alfabetizacao_2030`', 'mu.`meta_alfabetizacao_2030`')} AS meta_uf_2030_percentual,
           a.total_registros_alunos,
           'oficial' AS origem_indicador
    FROM {s.table('silver','municipio')} m
    {' '.join(joins)}"""
    cloud.step(run_id, "gold-indicador-municipio", lambda: cloud.query(sql_mun, "gold-municipio"))
    keys_uf = keys_for(cols["uf"], cols["meta_alfabetizacao_uf"], required=["_sigla_uf"])
    on_uf = " AND ".join(f"CAST(u.{k} AS STRING)=CAST(mu.{k} AS STRING)" for k in keys_uf)
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
