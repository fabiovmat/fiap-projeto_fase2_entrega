# Evidências exigidas

Após rodar na sua conta GCP, execute `python -m alfabetizacao.cli evidence`. Os JSONs gerados terão contagens e jobs.

Inclua **prints reais** do Console (não ilustrativos):

- `01_bucket_bronze.png`: pelo menos dois caminhos `run_id=...` de uma mesma fonte após duas execuções, provando histórico;
- `02_jobs_bigquery.png`: IDs e estados dos jobs de ingestão, Silver e Gold;
- `03_gold.png`: número de registros e amostra das tabelas Gold;
- `04_pubsub.png`: tópico e subscription, publicação e consumo;
- `05_eventos_gold.png`: registros na Gold e coluna de origem `simulado`;
- `06_quality_fail.png`: erro intencional bloqueante + registro em `ops.qualidade`;
- `07_monitoramento.png`: `ops.metricas` com duração, bytes e estado;
- `08_alerta.png`: envio real para um webhook (configure o ambiente);
- `09_finops.png`: tela Billing e relatório de custo ancorado em medidas.

Não versionar prints com IDs de conta, tokens, e-mail ou dados pessoais sensíveis.
