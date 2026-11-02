"""Mapeamento explícito e auditável de colunas (não inventar schema da fonte)."""
from dataclasses import dataclass

# Candidatos são verificações, nunca substitutos silenciosos; conferência em docs/esquema.json
CANDIDATES = {
    "ano": ("ano",),
    "id_municipio": ("id_municipio", "codigo_municipio"),
    "sigla_uf": ("sigla_uf", "uf"),
    "rede": ("rede", "id_rede", "tipo_rede"),
    "serie": ("serie", "id_serie", "ano_escolar"),
    "indicador": ("taxa_alfabetizacao", "indicador_alfabetizacao", "percentual_alfabetizacao", "percentual_alfabetizados", "percentual_alunos_alfabetizados", "percentual_alfabetizado"),
    "peso": ("peso_amostral", "peso_aluno", "peso"),
    "alfabetizado": ("alfabetizado", "indicador_alfabetizado", "aluno_alfabetizado"),
    "presenca": ("presenca", "presente", "indicador_presenca"),
}


def pick(columns, semantic, *, required=False):
    available = set(columns)
    matches = [candidate for candidate in CANDIDATES[semantic] if candidate in available]
    if matches:
        return matches[0]
    if required:
        raise ValueError(
            f"Coluna '{semantic}' não localizada. Disponíveis: {sorted(available)}. "
            "Verifique docs/esquema.json e ajuste CANDIDATES em src/alfabetizacao/schema.py"
        )
    return None


def sql_normalized(fields):
    """Acrescenta campos normalizados sem alterar a estrutura bruta da origem."""
    expr = []
    for sem in ("ano", "id_municipio", "sigla_uf", "rede", "serie"):
        column = pick(fields, sem)
        if column:
            val = f"CAST(`{column}` AS STRING)" if sem != "ano" else f"SAFE_CAST(`{column}` AS INT64)"
            if sem == "sigla_uf":
                val = f"UPPER(TRIM({val}))"
            elif sem in ("rede", "serie", "id_municipio"):
                val = f"TRIM({val})"
            expr.append(f"{val} AS _{sem}")
    if not expr:
        return "*"
    return "*, " + ", ".join(expr)


def numeric_field(columns, name):
    """Insiste em nome oficial, sem assumir valores ausentes como zero."""
    if name not in set(columns):
        return "CAST(NULL AS FLOAT64)"
    return f"SAFE_CAST(`{name}` AS FLOAT64)"


def planned_meta_year_columns(columns):
    return {y: f"meta_alfabetizacao_{y}" for y in range(2024, 2031) if f"meta_alfabetizacao_{y}" in set(columns)}
