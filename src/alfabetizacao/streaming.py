"""Streaming real no Pub/Sub com consumo incremental em micro-lotes e deduplicação."""
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from google.cloud import pubsub_v1, bigquery
from google.api_core.exceptions import AlreadyExists
from .cloud import Cloud, utcnow
from .quality import validate_event, latency_seconds, QualityError

LOG = logging.getLogger(__name__)


def create_resources(cloud: Cloud):
    s = cloud.s
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    topic_path = publisher.topic_path(s.project, s.topic)
    subscription_path = subscriber.subscription_path(s.project, s.subscription)
    try:
        publisher.create_topic(request={"name": topic_path})
    except AlreadyExists:
        pass
    try:
        subscriber.create_subscription(request={"name": subscription_path, "topic": topic_path})
    except AlreadyExists:
        pass
    LOG.info("Pub/Sub pronto: %s / %s", topic_path, subscription_path)


def publish(cloud: Cloud, count: int = 5, *, invalid=False, duplicate=False):
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(cloud.s.project, cloud.s.topic)
    last = None
    for i in range(count):
        event = {
            "event_id": uuid.uuid4().hex,
            "id_municipio": "3550308",  # código IBGE de São Paulo, apenas simulação
            "ano": 2026,
            "indicador": float(65+i) if not invalid else 150.0,
            "produced_at": utcnow().isoformat(),
            "origem": "simulado",
        }
        last = event
        publisher.publish(topic_path, json.dumps(event).encode("utf-8")).result(timeout=20)
        LOG.info("Publicado evento simulado %s", event["event_id"])
    if duplicate and last:
        publisher.publish(topic_path, json.dumps(last).encode("utf-8")).result(timeout=20)
        LOG.info("Duplicata intencional publicada: %s", last["event_id"])


def _save_raw(cloud: Cloud, payload_json: str):
    # Append imutável: duplicatas e inválidos também entram na Bronze, para auditoria.
    cloud.query(f"""INSERT INTO {cloud.s.table('bronze','eventos')}
        (receipt_id, payload_json, received_at)
        VALUES (@receipt, @payload, CURRENT_TIMESTAMP())""", "bronze-event-insert", params=[
        bigquery.ScalarQueryParameter("receipt", "STRING", uuid.uuid4().hex),
        bigquery.ScalarQueryParameter("payload", "STRING", payload_json),
    ])


def refresh_analytical_events(cloud: Cloud):
    s = cloud.s
    base = s.table("bronze", "eventos")
    sql = f"""CREATE OR REPLACE TABLE {s.table('silver','eventos')} AS
        WITH e AS (
          SELECT receipt_id, payload_json, received_at,
              JSON_VALUE(payload_json,'$.event_id') AS event_id,
              JSON_VALUE(payload_json,'$.id_municipio') AS id_municipio,
              SAFE_CAST(JSON_VALUE(payload_json,'$.ano') AS INT64) AS ano,
              SAFE_CAST(JSON_VALUE(payload_json,'$.indicador') AS FLOAT64) AS indicador,
              JSON_VALUE(payload_json,'$.origem') AS origem,
              SAFE_CAST(JSON_VALUE(payload_json,'$.produced_at') AS TIMESTAMP) AS produced_at
          FROM {base}
        )
        SELECT event_id, id_municipio, ano, indicador, origem, produced_at,
               received_at AS ingested_at,
               TIMESTAMP_DIFF(received_at, produced_at, MILLISECOND)/1000.0 AS latencia_seg
        FROM e WHERE event_id IS NOT NULL
             AND REGEXP_CONTAINS(id_municipio, r'^[0-9]{{7}}$')
             AND ano BETWEEN 2020 AND 2100
             AND indicador BETWEEN 0 AND 100
             AND origem = 'simulado'
             AND produced_at IS NOT NULL AND produced_at <= received_at
        QUALIFY ROW_NUMBER() OVER(PARTITION BY event_id ORDER BY received_at, receipt_id) = 1"""
    cloud.query(sql, "silver-eventos-deduplicados")
    cloud.query(
        f"CREATE OR REPLACE TABLE {s.table('gold','indicador_eventos')} AS "
        f"SELECT *, 'nao_oficial' AS categoria_fonte FROM {s.table('silver','eventos')}",
        "gold-eventos"
    )


def consume(cloud: Cloud, max_messages: int = 6, polls: int = 4):
    """Cada chamada processa micro-lotes, não um daemon sempre ligado."""
    sub = pubsub_v1.SubscriberClient()
    path = sub.subscription_path(cloud.s.project, cloud.s.subscription)
    received = 0
    run_id = "stream_" + uuid.uuid4().hex[:12]
    for _ in range(polls):
        response = sub.pull(request={"subscription": path, "max_messages": min(20, max_messages-received)}, timeout=20)
        if not response.received_messages:
            LOG.info("Nenhum evento aguardando neste micro-lote")
            continue
        acknowledged = []
        for item in response.received_messages:
            payload = item.message.data.decode("utf-8")
            # O ack somente ocorre depois de persistir o evento no BigQuery.
            try:
                cloud.step(run_id, "bronze-evento", lambda p=payload: _save_raw(cloud, p))
                ingested = utcnow()
                try:
                    event = json.loads(payload)
                    produced = validate_event(event)
                    latency = latency_seconds(produced, ingested)
                    cloud.quality(run_id, "evento_valido", "INFORMATIVA", 1, 1, True,
                                  f"evento={event['event_id']}; latencia_recebimento_s={latency:.3f}")
                except (QualityError, ValueError, TypeError, json.JSONDecodeError) as exc:
                    cloud.quality(run_id, "evento_invalido_quarentena", "INFORMATIVA", 0, 1, False, str(exc))
                acknowledged.append(item.ack_id)
                received += 1
            except Exception:
                LOG.exception("Falha ao persistir Bronze: mensagem NÃO será confirmada (redelivery)")
        if acknowledged:
            sub.acknowledge(request={"subscription": path, "ack_ids": acknowledged})
        cloud.step(run_id, "silver-gold-eventos", lambda: (refresh_analytical_events(cloud), None)[1])
        if received >= max_messages:
            break
    LOG.info("Mensagens processadas=%d; origem=simulado; verifique gold.indicador_eventos", received)
    return received
