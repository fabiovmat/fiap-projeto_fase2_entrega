"""Ingestão batch: Parquet imutável em GCS + tabelas externas Bronze + Silver."""
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .cloud import Cloud, utcnow
from .config import Settings, SOURCE, TABLES
from .schema import sql_normalized

LOG = logging.getLogger(__name__)


def run_identifier():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]


def schema_inventory(cloud: Cloud):
    inventory = {}
    for name in TABLES:
        tbl = cloud.bq.get_table(f"{SOURCE}.{name}")
        inventory[name] = [{"name": f.name, "type": f.field_type, "mode": f.mode} for f in tbl.schema]
    out = Path("docs/esquema.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOG.info("Esquemas oficiais salvos em %s", out)
    return inventory


def dry_run_sources(cloud: Cloud):
    result = {}
    for name in TABLES:
        # Estimativa antes de escanear tabelas (LIMIT não reduz bytes lidos).
        query = f"SELECT * FROM `{SOURCE}.{name}`"
        job = cloud.query(query, f"dry-run-{name}", dry_run=True)
        result[name] = {"estimated_bytes": job.total_bytes_processed or 0, "job_id": job.job_id}
    Path("docs").mkdir(exist_ok=True)
    Path("docs/dry-run.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    LOG.info("Dry-run salvo em docs/dry-run.json; ajuste MAX_BYTES_BILLED se necessário")
    return result


def ingest_one(cloud: Cloud, name: str, run_id: str):
    path = f"gs://{cloud.s.bucket}/bronze/{name}/run_id={run_id}/part-*.parquet"
    sql = f"""EXPORT DATA OPTIONS (uri='{path}', format='PARQUET', overwrite=false)
    AS SELECT * FROM `{SOURCE}.{name}`"""
    job = cloud.query(sql, f"export-{name}")
    # Ponte para o GCS histórico: somente o snapshot desta execução fica ativo.
    ext = f"""CREATE OR REPLACE EXTERNAL TABLE {cloud.s.table('bronze', name)}
    OPTIONS (format='PARQUET', uris=['{path}'])"""
    cloud.query(ext, f"bronze-external-{name}")
    return job


def silver_one(cloud: Cloud, name: str):
    fields = cloud.columns("bronze", name)
    select = sql_normalized(fields)
    # Silver mantém todos os campos de origem + chaves tipadas; não troca nulo por zero.
    return cloud.query(
        f"CREATE OR REPLACE TABLE {cloud.s.table('silver', name)} AS "
        f"SELECT {select} FROM {cloud.s.table('bronze', name)}",
        f"silver-{name}"
    )


def execute_batch(cloud: Cloud):
    run_id = run_identifier()
    cloud.insert_log("runs", {"run_id": run_id, "started_at": utcnow().isoformat(), "finished_at": None, "status": "INICIADO", "erro": None})
    try:
        cloud.step(run_id, "schema", lambda: (schema_inventory(cloud), None)[1])
        estimates = dry_run_sources(cloud)
        for name in TABLES:
            # Bloqueia scans acidentalmente altos antes da primeira leitura real.
            if estimates[name]["estimated_bytes"] > cloud.s.max_bytes:
                raise RuntimeError(f"Dry-run de {name}: {estimates[name]['estimated_bytes']} bytes excedem MAX_BYTES_BILLED")
            cloud.step(run_id, f"bronze-{name}", lambda n=name: ingest_one(cloud, n, run_id))
            cloud.step(run_id, f"silver-{name}", lambda n=name: silver_one(cloud, n))
        from .gold import validate_and_publish
        validate_and_publish(cloud, run_id)
        cloud.insert_log("runs", {"run_id": run_id, "started_at": None, "finished_at": utcnow().isoformat(), "status": "SUCESSO", "erro": None})
    except Exception as exc:
        cloud.insert_log("runs", {"run_id": run_id, "started_at": None, "finished_at": utcnow().isoformat(), "status": "FALHA", "erro": str(exc)[:4000]})
        cloud.alert(run_id, "batch", str(exc))
        raise
    return run_id
