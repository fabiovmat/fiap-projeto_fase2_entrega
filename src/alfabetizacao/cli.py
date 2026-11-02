"""Interface por comandos para o avaliador reproduzir o projeto."""
import argparse
import json
import logging
from pathlib import Path
from .cloud import Cloud
from .config import Settings
from .batch import execute_batch, schema_inventory, dry_run_sources
from .streaming import create_resources, publish, consume, refresh_analytical_events


def main():
    parser = argparse.ArgumentParser(prog="python -m alfabetizacao.cli")
    parser.add_argument("command", choices=[
        "init", "schema", "dry-run", "batch", "pubsub-init", "publish", "consume", "stream-refresh", "evidence", "finops", "quality-fail-demo", "export-phase3",
    ])
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--invalid", action="store_true")
    parser.add_argument("--duplicate", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cloud = Cloud(Settings.from_env())
    if args.command == "init":
        cloud.init()
    elif args.command == "schema":
        schema_inventory(cloud)
    elif args.command == "dry-run":
        dry_run_sources(cloud)
    elif args.command == "batch":
        print("RUN_ID:", execute_batch(cloud))
    elif args.command == "pubsub-init":
        create_resources(cloud)
    elif args.command == "publish":
        publish(cloud, count=args.count, invalid=args.invalid, duplicate=args.duplicate)
    elif args.command == "consume":
        consume(cloud, max_messages=args.count)
    elif args.command == "stream-refresh":
        refresh_analytical_events(cloud)
    elif args.command == "evidence":
        folder = Path("docs/evidencias")
        folder.mkdir(exist_ok=True)
        queries = {
            "01_execucoes": f"SELECT * FROM {cloud.s.table('ops','runs')} ORDER BY COALESCE(finished_at,started_at) DESC LIMIT 30",
            "02_metricas": f"SELECT * FROM {cloud.s.table('ops','metricas')} ORDER BY inicio DESC LIMIT 100",
            "03_qualidade": f"SELECT * FROM {cloud.s.table('ops','qualidade')} ORDER BY checked_at DESC LIMIT 100",
            "04_alertas": f"SELECT * FROM {cloud.s.table('ops','alertas')} ORDER BY momento DESC LIMIT 100",
            "05_gold_municipio": f"SELECT * FROM {cloud.s.table('gold','indicador_municipio')} LIMIT 30",
            "06_gold_eventos": f"SELECT * FROM {cloud.s.table('gold','indicador_eventos')} LIMIT 30",
        }
        for filename, sql in queries.items():
            try:
                rows = [dict(row.items()) for row in cloud.rows(sql, filename)]
                serialized = json.dumps(rows, ensure_ascii=False, indent=2, default=str)
                (folder / (filename + ".json")).write_text(serialized + "\n", encoding="utf-8")
                print(filename, len(rows))
            except Exception as exc:
                logging.error("Não foi possível extrair %s: %s", filename, exc)
        print("Faça também prints do console BigQuery, Pub/Sub e Cloud Storage: docs/evidencias/")
    elif args.command == "export-phase3":
        from .batch import run_identifier
        run_id = run_identifier()
        uri = f"gs://{cloud.s.bucket}/gold/indicador_municipio/run_id={run_id}/part-*.parquet"
        job = cloud.query(
            f"EXPORT DATA OPTIONS(uri='{uri}',format='PARQUET',overwrite=false) AS "
            f"SELECT * FROM {cloud.s.table('gold','indicador_municipio')}",
            "export-phase3")
        print(f"Gold versionada para fase 3: {uri} | job_id={job.job_id}")
    elif args.command == "quality-fail-demo":
        from .quality import QualityError
        try:
            cloud.quality("demo-falha", "join_teste_controlado", "BLOQUEANTE", 0.60, 0.80, False,
                          "Execução intencional: 60% de correspondência, mínimo 80%")
        except QualityError as exc:
            cloud.alert("demo-falha", "quality-fail-demo", "export-phase3", str(exc))
            raise
    elif args.command == "finops":
        from .finops import make_report
        make_report(cloud)


if __name__ == "__main__":
    main()
