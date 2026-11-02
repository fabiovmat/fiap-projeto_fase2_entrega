"""Configuração central; sem credenciais fixadas no código."""
import os
import re
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()
TABLES = (
    "uf", "meta_alfabetizacao_brasil", "meta_alfabetizacao_uf",
    "meta_alfabetizacao_municipio", "municipio", "alunos", "dicionario",
)
SOURCE = "basedosdados.br_inep_avaliacao_alfabetizacao"
SAFE_ID = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{3,62}$")


@dataclass(frozen=True)
class Settings:
    project: str
    bucket: str
    location: str = "US"
    topic: str = "alfabetizacao-eventos"
    subscription: str = "alfabetizacao-consumer"
    max_bytes: int = 1073741824
    match_threshold: float = 0.8
    alert_webhook: str = ""

    @classmethod
    def from_env(cls):
        project = os.getenv("GCP_PROJECT_ID", "")
        bucket = os.getenv("GCS_BUCKET", "")
        if not project or not bucket or not SAFE_ID.fullmatch(project):
            raise ValueError("Defina GCP_PROJECT_ID e GCS_BUCKET válidos no .env")
        threshold = float(os.getenv("MIN_JOIN_MATCH_RATE", "0.80"))
        if not (0 < threshold <= 1):
            raise ValueError("MIN_JOIN_MATCH_RATE deve estar entre 0 e 1")
        return cls(
            project=project, bucket=bucket,
            location=os.getenv("BQ_LOCATION", "US"),
            topic=os.getenv("PUBSUB_TOPIC", "alfabetizacao-eventos"),
            subscription=os.getenv("PUBSUB_SUBSCRIPTION", "alfabetizacao-consumer"),
            max_bytes=int(os.getenv("MAX_BYTES_BILLED", "1073741824")),
            match_threshold=threshold,
            alert_webhook=os.getenv("ALERT_WEBHOOK_URL", ""),
        )

    def table(self, layer, name):
        if layer not in {"bronze", "silver", "gold", "ops"} or name not in TABLES + (
            "indicador_municipio", "indicador_uf", "metas_brasil", "alunos_resumo",
            "indicador_eventos", "eventos", "runs", "metricas", "qualidade", "alertas"
        ):
            raise ValueError(f"Tabela não autorizada: {layer}.{name}")
        return f"`{self.project}.{layer}.{name}`"
