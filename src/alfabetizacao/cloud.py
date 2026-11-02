"""Conectores GCP e observabilidade persistida no BigQuery."""
import json
import logging
import time
import urllib.request
from datetime import datetime, timezone
from google.cloud import bigquery, storage
from .config import Settings

LOG = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc)


class Cloud:
    def __init__(self, settings: Settings):
        self.s = settings
        self.bq = bigquery.Client(project=settings.project, location=settings.location)
        self.gcs = storage.Client(project=settings.project)

    def query(self, sql, label, *, dry_run=False, params=None):
        job_config = bigquery.QueryJobConfig(
            dry_run=dry_run,
            use_query_cache=False,
            maximum_bytes_billed=self.s.max_bytes,
            query_parameters=params or [],
        )
        job = self.bq.query(sql, location=self.s.location, job_config=job_config)
        if not dry_run:
            job.result()
        bytes_ = job.total_bytes_processed or 0
        LOG.info("%s | job=%s | processed=%s bytes | dry_run=%s", label, job.job_id, bytes_, dry_run)
        return job

    def rows(self, sql, label):
        return list(self.query(sql, label).result())

    def init(self):
        for name in ("bronze", "silver", "gold", "ops"):
            dataset = bigquery.Dataset(f"{self.s.project}.{name}")
            dataset.location = self.s.location
            self.bq.create_dataset(dataset, exists_ok=True)
        ddl = {
            "runs": "run_id STRING, started_at TIMESTAMP, finished_at TIMESTAMP, status STRING, erro STRING",
            "metricas": "run_id STRING, etapa STRING, status STRING, inicio TIMESTAMP, fim TIMESTAMP, duracao_s FLOAT64, linhas_entrada INT64, linhas_saida INT64, bytes_processados INT64, job_id STRING, mensagem STRING",
            "qualidade": "run_id STRING, regra STRING, classificacao STRING, valor FLOAT64, limite FLOAT64, status STRING, checked_at TIMESTAMP, detalhes STRING",
            "alertas": "run_id STRING, momento TIMESTAMP, etapa STRING, mensagem STRING, webhook_enviado BOOL",
            "eventos": "event_id STRING, id_municipio STRING, ano INT64, indicador FLOAT64, origem STRING, produced_at TIMESTAMP, ingested_at TIMESTAMP, latencia_seg FLOAT64",
        }
        self.query(f"CREATE TABLE IF NOT EXISTS {self.s.table('bronze','eventos')} "
                   "(receipt_id STRING, payload_json STRING, received_at TIMESTAMP)", "init-bronze-eventos")
        for name, fields in ddl.items():
            self.query(f"CREATE TABLE IF NOT EXISTS {self.s.table('ops', name)} ({fields})", f"init-{name}")

    def insert_log(self, table, data):
        target = f"{self.s.project}.ops.{table}"
        errors = self.bq.insert_rows_json(target, [data])
        if errors:
            raise RuntimeError(f"Não foi possível persistir {target}: {errors}")

    def step(self, run_id, label, fn):
        started = utcnow()
        try:
            result = fn()
        except Exception as exc:
            self._metric(run_id, label, "FALHA", started, None, str(exc))
            self.alert(run_id, label, str(exc))
            raise
        self._metric(run_id, label, "OK", started, result, "")
        return result

    def _metric(self, run_id, label, status, started, job, message):
        end = utcnow()
        lines_out = None
        if job is not None:
            candidates = []
            if label.startswith("silver-"):
                candidates.append(("silver", label[len("silver-"):].replace("-", "_")))
            if label.startswith("gold-"):
                candidates.append(("gold", label[len("gold-"):].replace("-", "_")))
            mapping = {"indicador-municipio":"indicador_municipio", "indicador-uf":"indicador_uf",
                       "metas-brasil":"metas_brasil", "alunos-resumo":"alunos_resumo"}
            if label.startswith("gold-"):
                candidates = [("gold", mapping.get(label[len("gold-"):], label[len("gold-"):].replace("-", "_")))]
            try:
                for layer, table in candidates:
                    lines_out = self.bq.get_table(f"{self.s.project}.{layer}.{table}").num_rows
            except Exception:
                pass
        self.insert_log("metricas", {
            "run_id": run_id, "etapa": label, "status": status,
            "inicio": started.isoformat(), "fim": end.isoformat(),
            "duracao_s": (end-started).total_seconds(),
            "linhas_entrada": None, "linhas_saida": lines_out,
            "bytes_processados": (job.total_bytes_processed or 0) if job is not None else 0,
            "job_id": job.job_id if job is not None else None,
            "mensagem": message[:4000],
        })

    def quality(self, run_id, name, kind, value, threshold, passed, details=""):
        self.insert_log("qualidade", {
            "run_id": run_id, "regra": name, "classificacao": kind,
            "valor": float(value), "limite": float(threshold),
            "status": "OK" if passed else "FALHA", "checked_at": utcnow().isoformat(),
            "detalhes": details[:4000],
        })
        if not passed and kind == "BLOQUEANTE":
            from .quality import QualityError
            raise QualityError(f"Regra bloqueante {name} falhou: valor={value}, limite={threshold}. {details}")

    def alert(self, run_id, step, error):
        delivered = False
        if self.s.alert_webhook:
            payload = json.dumps({"text": f"[FIAP alfabetização] Falha {run_id} / {step}: {error[:600]}"}).encode()
            try:
                req = urllib.request.Request(
                    self.s.alert_webhook, payload, headers={"Content-Type": "application/json"}, method="POST"
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    delivered = 200 <= response.status < 300
            except Exception:
                LOG.exception("Erro no webhook de alerta")
        else:
            LOG.warning("ALERT_WEBHOOK_URL não configurada: nenhuma notificação externa enviada")
        self.insert_log("alertas", {
            "run_id": run_id, "momento": utcnow().isoformat(), "etapa": step,
            "mensagem": error[:4000], "webhook_enviado": delivered,
        })

    def columns(self, layer, name):
        return [field.name for field in self.bq.get_table(f"{self.s.project}.{layer}.{name}").schema]

    def bucket_size(self):
        objects = list(self.gcs.list_blobs(self.s.bucket, prefix="bronze/"))
        return sum(obj.size or 0 for obj in objects), len(objects)
