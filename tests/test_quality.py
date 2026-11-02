import pytest
from datetime import datetime, timedelta, timezone
from alfabetizacao.quality import QualityError, rate_matched, require_match, meta_status, validate_event, latency_seconds
from alfabetizacao.schema import pick, sql_normalized, planned_meta_year_columns


def test_match_rate_and_blocking():
    assert rate_matched(10, 9) == .9
    with pytest.raises(QualityError):
        require_match(100, 70, .8, "municipio-meta")


def test_meta_missing_is_not_failure():
    assert meta_status(50, None) == "sem_dado"
    assert meta_status(85, 80) == "atingiu"
    assert meta_status(70, 80) == "nao_atingiu"


def test_bad_event_rejected_and_actual_latency():
    when = datetime.now(timezone.utc) - timedelta(seconds=7)
    event = {"event_id": "x", "id_municipio": "3550308", "ano": 2026,
             "indicador": 70.0, "origem": "simulado", "produced_at": when.isoformat()}
    assert latency_seconds(validate_event(event), datetime.now(timezone.utc)) >= 7
    event["indicador"] = 150
    with pytest.raises(QualityError):
        validate_event(event)


def test_schema_fails_explicitly():
    with pytest.raises(ValueError, match="não localizada"):
        pick(["foo"], "indicador", required=True)
    assert "_sigla_uf" in sql_normalized(["ano", "sigla_uf"])
    assert planned_meta_year_columns(["meta_alfabetizacao_2030"])[2030] == "meta_alfabetizacao_2030"
