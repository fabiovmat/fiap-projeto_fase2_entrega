"""Regras puras usadas na pipeline e testáveis sem GCP."""
from datetime import datetime, timezone


class QualityError(RuntimeError):
    pass


def rate_matched(total: int, matched: int) -> float:
    if total < 0 or matched < 0 or matched > total:
        raise ValueError("Contagens inválidas")
    return matched / total if total else 0.0


def require_match(total: int, matched: int, minimum: float, context: str) -> float:
    rate = rate_matched(total, matched)
    if rate < minimum:
        raise QualityError(f"{context}: match {rate:.1%} abaixo do mínimo {minimum:.1%}")
    return rate


def meta_status(realizado, meta):
    if realizado is None or meta is None:
        return "sem_dado"
    return "atingiu" if realizado >= meta else "nao_atingiu"


def validate_event(e: dict):
    must = ("event_id", "id_municipio", "ano", "indicador", "produced_at", "origem")
    if any(k not in e for k in must):
        raise QualityError("Evento sem campos obrigatórios")
    if e["origem"] != "simulado":
        raise QualityError("Eventos do produtor devem ter origem 'simulado'")
    if not isinstance(e["event_id"], str) or not e["event_id"].strip():
        raise QualityError("event_id inválido")
    if not str(e["id_municipio"]).isdigit() or len(str(e["id_municipio"])) != 7:
        raise QualityError("id_municipio precisa ter 7 dígitos")
    if not isinstance(e["ano"], int) or not 2020 <= e["ano"] <= 2100:
        raise QualityError("Ano fora do intervalo")
    if not isinstance(e["indicador"], (float, int)) or isinstance(e["indicador"], bool) or not 0 <= e["indicador"] <= 100:
        raise QualityError("Indicador precisa estar entre 0 e 100")
    try:
        produced = datetime.fromisoformat(e["produced_at"].replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise QualityError("produced_at inválido") from exc
    if produced.tzinfo is None:
        raise QualityError("produced_at sem fuso horário")
    if produced > datetime.now(timezone.utc):
        raise QualityError("produced_at no futuro")
    return produced


def latency_seconds(produced: datetime, ingested: datetime) -> float:
    seconds = (ingested - produced).total_seconds()
    if seconds < 0:
        raise QualityError("Latência negativa; relógios fora de sincronia")
    return seconds
