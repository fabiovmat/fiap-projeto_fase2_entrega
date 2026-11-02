"""Estimativa mensal com quantidades medidas no próprio ambiente GCP."""
import json
from datetime import datetime, timezone
from pathlib import Path
from .cloud import Cloud

USD_PER_TIB_BQ = 6.25   # parâmetro de tabela de preços; conferir sempre a região
USD_PER_GIB_GCS_MONTH = 0.020  # referência aproximada para Standard regional US
TIB = 1024 ** 4
GIB = 1024 ** 3


def make_report(cloud: Cloud):
    s = cloud.s
    records = cloud.rows(
        f"""SELECT run_id, SUM(COALESCE(bytes_processados,0)) bytes_processados,
                   SUM(COALESCE(duracao_s,0)) duracao_segundos,
                   COUNT(*) etapas
          FROM {s.table('ops','metricas')} WHERE etapa LIKE 'bronze-%' OR etapa LIKE 'silver-%' OR etapa LIKE 'gold-%'
          GROUP BY run_id ORDER BY run_id DESC LIMIT 10""", "finops-metricas"
    )
    runs = [dict(r.items()) for r in records if not str(r["run_id"]).startswith("stream_")]
    if not runs:
        raise RuntimeError("Sem medições de um batch real. Execute 'batch' antes de 'finops'.")
    latest = runs[0]
    bytes_batch = int(latest["bytes_processados"])
    blob_bytes, object_count = cloud.bucket_size()
    cadence = 4  # 4 batches/mês (premissa explícita)
    events_month = 300  # 10 por dia (premissa explícita, não medição)
    bq_tib_month = bytes_batch * cadence / TIB
    storage_gib = blob_bytes / GIB
    # Projeção bruta, antes de franquias; storage crescerá conforme snapshots se acumularem.
    cost_bq = bq_tib_month * USD_PER_TIB_BQ
    cost_storage = storage_gib * USD_PER_GIB_GCS_MONTH
    report = f"""# FinOps — medição do ambiente GCP

Data da medição: {datetime.now(timezone.utc).isoformat()}
Projeto: `{s.project}` | Localização: `{s.location}`
Último run observado: `{latest['run_id']}`

| Serviço | Unidade | Quantidade medida / premissa | Preço unitário de referência | Custo mensal bruto (USD) |
|---|---|---:|---:|---:|
| BigQuery, consultas | TiB processados | {bq_tib_month:.8f} (medição de {bytes_batch:,} bytes/execução × {cadence} execuções/mês) | {USD_PER_TIB_BQ:.2f} USD/TiB | {cost_bq:.6f} |
| Cloud Storage Standard | GiB armazenados | {storage_gib:.6f} GiB medidos, {object_count} objetos | {USD_PER_GIB_GCS_MONTH:.3f} USD/GiB-mês | {cost_storage:.6f} |
| Pub/Sub | mensagens/mês | {events_month} (premissa, sem medição de throughput) | **A calcular por bytes de mensagens** | N/D |
| BigQuery armazenamento Silver/Gold | GiB-mês | **não medido neste relatório** | consultar tabela de preços | N/D |
| Egress entre regiões | GiB | mesma multirregião US no desenho | depende de localizações reais | N/D |

**Subtotal parcial bruto de serviços medidos:** USD {cost_bq+cost_storage:.6f}/mês.
**Este subtotal NÃO é o custo total da arquitetura.** Não inclui armazenamento BigQuery, operações de GCS, mensagens Pub/Sub, saídas de rede e eventuais serviços adicionais. Verificar descontos/franquias no billing real.

- BigQuery cobra por processamento de consultas. A franquia anunciada de 1 TiB/mês e 10 GiB de armazenamento é compartilhada conforme as regras da conta de faturamento, não um crédito exclusivo deste repositório.
- O tamanho GCS acima é o acumulado **atual** da Bronze. Com quatro snapshots novos por mês, o volume cresce; acompanhar crescimento real e definir retenção conforme exigência de histórico.
- Preços de referência são simplificações: consultar [BigQuery](https://cloud.google.com/bigquery/pricing), [Cloud Storage](https://cloud.google.com/storage/pricing), [Pub/Sub](https://cloud.google.com/pubsub/pricing) e calculadora da região.
- Para informar preço exato e uso em produção, complemente com o Billing do projeto, custo de armazenamento BigQuery e bytes medidos do Pub/Sub.
"""
    out = Path("docs/finops-medido.md")
    out.write_text(report, encoding="utf-8")
    Path("docs/finops-medido.json").write_text(json.dumps({"runs":runs,"gcs_bytes":blob_bytes,"gcs_objects":object_count},indent=2,default=str), encoding="utf-8")
    print(f"Medição salva em {out}; custo parcial bruto US$ {cost_bq+cost_storage:.6f}/mês")
