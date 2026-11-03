# Tech Challenge FIAP — Fase 2
## Pipeline híbrido para análise da alfabetização no Brasil

**Pós-Tech FIAP — Tech Challenge, Fase 2**  
**Responsável:** Fabio Verissimo  
**Repositório:** [fabiovmat/fiap-projeto_fase2_entrega](https://github.com/fabiovmat/fiap-projeto_fase2_entrega)  
**Apresentação executiva:** [Vídeo do projeto (até 5 minutos)](https://youtu.be/_h3-h79YDRE)  
**Execução documentada:** 02/11/2026 — Google Cloud Platform

## 1. Contexto e objetivo

O projeto implementa uma pipeline híbrida de Engenharia de Dados para integrar informações públicas sobre alfabetização no Brasil, indicadores territoriais e metas educacionais. A arquitetura combina ingestão em lote de dados oficiais com eventos simulados transmitidos pelo Pub/Sub, disponibilizando resultados analíticos no BigQuery com rastreabilidade operacional.

O Compromisso Nacional Criança Alfabetizada busca assegurar a alfabetização ao final do 2º ano do ensino fundamental. Conforme o enunciado da FIAP, a referência da Pesquisa Alfabetiza Brasil (2023) é de **743 pontos na escala Saeb**. A meta pactuada para 2030 na rede pública é de **80%**; a universalização da alfabetização constitui um objetivo mais amplo e não é tratada como a mesma meta contratual.

**Fonte:** [Base dos Dados — Avaliação da Alfabetização](https://basedosdados.org/dataset/073a39d4-89cf-4068-b1e8-34ed0d9c0b72)  
**BigQuery de origem:** `basedosdados.br_inep_avaliacao_alfabetizacao`

| Tabela de origem | Aplicação |
|---|---|
| `alunos` | Microdados, agrupados para avaliação de cobertura dos indicadores territoriais |
| `municipio` | Indicadores municipais por ano, rede e série |
| `uf` | Indicadores por unidade federativa |
| `meta_alfabetizacao_brasil` | Trajetória nacional de metas |
| `meta_alfabetizacao_uf` | Metas estaduais |
| `meta_alfabetizacao_municipio` | Metas municipais |
| `dicionario` | Interpretação oficial de códigos e categorias |

As seis entidades previstas no desafio são processadas, além do dicionário de apoio.

## 2. Arquitetura da solução

~~~mermaid
flowchart TD
    F[Base dos Dados / BigQuery] --> B[Ingestão Batch em Python]
    B --> GCS[Cloud Storage / Bronze / Parquet versionado]
    GCS --> BR[BigQuery / tabelas externas Bronze]
    BR --> SI[BigQuery / Silver padronizada]
    SI --> Q{Qualidade e correspondência de joins}
    Q -->|Regras aprovadas| GO[BigQuery / Gold oficial]
    Q -->|Falha bloqueante| OP[BigQuery / ops]
    P[Produtor de eventos simulados] --> PS[Pub/Sub]
    PS --> C[Consumidor Python / micro-lotes]
    C --> BE[BigQuery / Bronze de eventos]
    BE --> SE[Silver / validação e deduplicação]
    SE --> GE[Gold / eventos não oficiais]
    B --> OP
    C --> OP
    OP --> SL[Webhook Slack / alertas]
    GO --> EX[Exportação Parquet / Fase 3]
~~~

| Componente | Implementação |
|---|---|
| **Bronze** | Snapshots históricos em Parquet no Cloud Storage, vinculados a `run_id`; tabelas externas BigQuery e eventos brutos persistidos por append |
| **Silver** | Normalização de campos e chaves, preservação das informações de origem e agregação dos microdados para comparação |
| **Gold** | Indicadores oficiais territoriais, metas, resumo de alunos, dicionário e tabela separada de eventos simulados |
| **Ops** | Histórico de execuções, métricas dos jobs, regras de qualidade e alertas em BigQuery |
| **Streaming** | Pub/Sub com produção e consumo em micro-lotes, filtro de eventos inválidos e deduplicação por `event_id` |
| **Observabilidade** | Persistência operacional, identificação de falhas e notificação externa via webhook Slack |

O Batch utiliza snapshots e recria Silver/Gold com base na ingestão atual. A Bronze conserva snapshots anteriores. O consumo do Pub/Sub é acionado por comando; não há consumidor contínuo nem orquestração periódica automática neste protótipo.

### Tecnologias

Python 3.10+, Google BigQuery, Google Cloud Storage, Google Pub/Sub, Google Cloud Shell, Pytest, Git e GitHub.

## 3. Organização do repositório

~~~text
fiap-projeto_fase2_entrega/
├── .env.example
├── .gitignore
├── README.md
├── pyproject.toml
├── requirements.txt
├── scripts/
│   ├── init_git.sh
│   ├── setup_gcp.sh
│   └── verificar.sh
├── src/alfabetizacao/
│   ├── __init__.py
│   ├── batch.py
│   ├── cli.py
│   ├── cloud.py
│   ├── config.py
│   ├── finops.py
│   ├── gold.py
│   ├── quality.py
│   ├── rede.py
│   ├── schema.py
│   └── streaming.py
├── tests/
│   ├── test_gold_coverage.py
│   ├── test_quality.py
│   └── test_rede.py
└── docs/
    ├── diagnostico-cobertura-alunos.md
    ├── diagnostico-rede.md
    ├── dry-run.json
    ├── esquema.json
    ├── finops-medido.md
    ├── finops-medido.json
    └── evidencias/
        ├── 01_execucoes.json
        ├── 02_metricas.json
        ├── 03_qualidade.json
        ├── 04_alertas.json
        ├── 05_gold_municipio.json
        ├── 06_gold_eventos.json
        ├── 08_batch_completo_sucesso.log
        ├── 10_streaming_consume.log
        ├── 12_evento_invalido_consume.log
        ├── 13_alerta_slack.log
        ├── 14_alerta_slack.png
        └── 15_armazenamento_bigquery.txt
~~~

## 4. Execução comprovada no Google Cloud

**Projeto GCP:** `project-69677cc7-ad0d-49e4-b6f`  
**Bucket:** `gs://fiap-projeto_fase2_entrega/`  
**Run do Batch completo:** `20261102T213746Z_f9941625`  
**Resultado:** `SUCESSO`, iniciado às 21:37:46 e concluído às 21:39:12 UTC de 02/11/2026.

| Indicador | Resultado |
|---|---:|
| Registros em `silver.municipio` | 23.995 |
| Registros em `gold.indicador_municipio` | 23.995 |
| Chaves municipais analíticas duplicadas | 0 |
| Taxa de match de microdados nas redes individuais comparáveis | 94,49% |
| Cobertura histórica incluindo redes agregadas | 51,71% — informativa |
| Eventos recebidos na Bronze do streaming | 7 |
| Eventos válidos e únicos na Gold do streaming | 5 |
| Duplicações na Gold do streaming | 0 |
| Eventos inválidos excluídos da camada analítica | 1 |
| Latência média dos eventos válidos na Gold | 18,538 s |
| Testes Python executados | 20 aprovados |

Os **23.995 registros** correspondem a combinações de município, ano, rede e série; não equivalem à quantidade de municípios brasileiros distintos.

### Qualidade e integridade referencial

As regras bloqueantes verificam nulidade em chaves, unicidade, faixa percentual e correspondência nos relacionamentos pertinentes. O limiar configurado é de **80%**.

A análise identificou uma diferença de granularidade entre indicadores municipais e microdados de alunos: códigos de rede **0 (total)** e **5 (rede pública agregada)** não possuem correspondência direta com redes individuais dos microdados. Por isso, a cobertura histórica geral de **51,71%** é registrada como informativa, enquanto o universo de redes individuais comparáveis alcança **94,49%** e permanece sujeito a bloqueio. As verificações por ano, rede e série também são bloqueantes.

As redes agregadas permanecem representadas na Gold. Ausência de correspondência individual é representada por `NULL`, não por zero alunos. Os indicadores de alfabetização oficiais não são recalculados como médias simples das contagens de microdados.

Detalhes: [Diagnóstico de redes](docs/diagnostico-rede.md) e [Diagnóstico de cobertura](docs/diagnostico-cobertura-alunos.md).

### Streaming simulado

O produtor utiliza eventos marcados com `origem=simulado`. O consumo persiste as entregas na Bronze, incluindo duplicatas e mensagens inválidas. Silver e Gold mantêm apenas eventos válidos e únicos por `event_id`, com `categoria_fonte=nao_oficial`.

O ensaio contemplou cinco eventos válidos, uma duplicata e um evento propositalmente inválido com indicador de 150%. O evento inválido permaneceu na Bronze e foi excluído do resultado analítico, com registro da rejeição em `ops.qualidade`.

### Observabilidade e alertas

As tabelas `ops.runs`, `ops.metricas`, `ops.qualidade` e `ops.alertas` armazenam os registros operacionais. A demonstração de falha controlada utilizou **60% de correspondência**, abaixo do limite bloqueante de **80%**. A regra gerou exceção, persistiu o alerta no BigQuery e o webhook enviou a notificação ao Slack (`webhook_enviado=true`).

Evidências: [Batch completo](docs/evidencias/08_batch_completo_sucesso.log), [histórico de execuções](docs/evidencias/01_execucoes.json), [qualidade](docs/evidencias/03_qualidade.json), [alertas](docs/evidencias/04_alertas.json) e [captura do Slack](docs/evidencias/14_alerta_slack.png).

## 5. Produtos analíticos e consultas

| Tabela Gold | Finalidade |
|---|---|
| `gold.indicador_municipio` | Indicadores municipais, metas pactuadas, distância até a meta, situação e contagem de registros de alunos quando comparáveis |
| `gold.indicador_uf` | Indicadores estaduais e metas do recorte público pertinente |
| `gold.metas_brasil` | Trajetória nacional das metas |
| `gold.alunos_resumo` | Contagem de microdados agrupados, sem atribuir a ela uma taxa ponderada |
| `gold.dicionario` | Decodificação de categorias da fonte |
| `gold.indicador_eventos` | Indicadores simulados, separados dos dados oficiais |

Exemplo de consulta de integridade na Gold:

~~~sql
WITH chaves AS (
  SELECT id_municipio, ano, rede_codigo, serie_codigo,
         COUNT(*) AS ocorrencias
  FROM `project-69677cc7-ad0d-49e4-b6f.gold.indicador_municipio`
  GROUP BY 1, 2, 3, 4
)
SELECT
  SUM(ocorrencias) AS total_registros,
  COUNT(*) AS chaves_distintas,
  COUNTIF(ocorrencias > 1) AS chaves_duplicadas
FROM chaves;
~~~

Resultado documentado: **23.995 registros, 23.995 chaves distintas e zero chaves duplicadas**.

A meta ausente não é convertida em zero: a coluna `status_meta_2030` retorna `sem_dado` quando não há informação suficiente. A distância até a meta é registrada em pontos percentuais, respeitando os recortes oficiais de rede e período.

## 6. FinOps

Foram medidos os volumes de armazenamento do ambiente e registrados os bytes processados por jobs BigQuery.

| Serviço | Medição |
|---|---:|
| BigQuery — armazenamento lógico aproximado das tabelas | **0,339439 GiB** |
| Cloud Storage — volume de objetos no momento da coleta | **204.451.589 bytes (0,190410 GiB)** |
| Projeção de consultas | **4 execuções Batch/mês** — hipótese de operação |
| Projeção de streaming | **300 mensagens/mês** — hipótese de operação |
| Subtotal mensal bruto dos componentes quantificados | **aprox. US$ 0,02605** |

O valor é uma **projeção parcial**, anterior a franquias gratuitas e créditos promocionais; **não representa faturamento efetivo**. A parcela de Cloud Storage da projeção utiliza uma hipótese de localização regional e preço de referência, sujeita à confirmação. Custos de operações, tráfego e throughput Pub/Sub não foram integralmente mensurados. O histórico de snapshots pode aumentar o armazenamento ao longo do tempo.

A arquitetura utiliza BigQuery sob demanda, estimativas de leitura com `dry-run`, limite de bytes faturáveis por consulta e arquivos Parquet, sem clusters permanentes.

Relatório completo: [FinOps medido](docs/finops-medido.md) · [Métricas coletadas](docs/evidencias/02_metricas.json) · [Medição de armazenamento](docs/evidencias/15_armazenamento_bigquery.txt).

## 7. Reprodutibilidade

### Pré-requisitos

- Python 3.10+ e ferramentas `git`, `gcloud` e `bq`;
- projeto Google Cloud com faturamento habilitado e permissões adequadas para BigQuery, Cloud Storage e Pub/Sub;
- autenticação da conta com acesso às APIs e às tabelas públicas da Base dos Dados.

### Instalação

~~~bash
git clone https://github.com/fabiovmat/fiap-projeto_fase2_entrega.git
cd fiap-projeto_fase2_entrega
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
cp .env.example .env
~~~

Configurações do `.env`:

~~~dotenv
GCP_PROJECT_ID=seu-projeto-gcp
BQ_LOCATION=US
GCS_LOCATION=us-central1
GCS_BUCKET=seu-bucket-globalmente-unico
PUBSUB_TOPIC=alfabetizacao-eventos
PUBSUB_SUBSCRIPTION=alfabetizacao-consumer
MAX_BYTES_BILLED=1073741824
MIN_JOIN_MATCH_RATE=0.80
ALERT_WEBHOOK_URL=
~~~

A variável `ALERT_WEBHOOK_URL` é opcional para execução sem alertas externos; seu token real não é versionado. O arquivo `.env` permanece fora do Git.

### Testes e criação dos recursos

~~~bash
python -m pip check
python -m pytest -q
bash scripts/setup_gcp.sh
python -m alfabetizacao.cli schema
python -m alfabetizacao.cli dry-run
~~~

### Pipeline Batch

~~~bash
python -m alfabetizacao.cli batch
~~~

O Batch lê os dados públicos, grava snapshots Parquet na Bronze, normaliza a Silver, aplica regras bloqueantes e publica as tabelas Gold após aprovação das validações.

### Streaming simulado

~~~bash
python -m alfabetizacao.cli pubsub-init
python -m alfabetizacao.cli publish --count 5 --duplicate
python -m alfabetizacao.cli consume --count 6
python -m alfabetizacao.cli publish --count 1 --invalid
python -m alfabetizacao.cli consume --count 1
~~~

### Evidências e cenários operacionais

~~~bash
python -m alfabetizacao.cli evidence
python -m alfabetizacao.cli export-phase3
~~~

O comando `quality-fail-demo` é uma demonstração isolada de falha bloqueante, com taxa de 60% e limite de 80%; termina intencionalmente com uma exceção e registra o alerta:

~~~bash
python -m alfabetizacao.cli quality-fail-demo
~~~

A execução do Batch, a exportação e os comandos de streaming acessam recursos reais de nuvem e podem gerar consumo faturável. O comando `finops` regenera `docs/finops-medido.md` a partir do modelo automático do projeto, substituindo o relatório complementar documentado neste repositório.

## 8. Evidências e continuidade para a Fase 3

As evidências de execução estão disponíveis em [docs/evidencias](docs/evidencias), incluindo JSONs operacionais, amostras Gold, logs Batch/Streaming e captura da notificação recebida no Slack.

A versão da Gold exportada em Parquet para a Fase 3 está registrada em:

`gs://fiap-projeto_fase2_entrega/gold/indicador_municipio/run_id=20261102T220143Z_f35fc64a/part-*.parquet`

**Job de exportação:** `bdf79cb6-ebcd-4226-8322-abf4d187be0f`.

A base pode apoiar análises territoriais e desenvolvimento futuro de modelos preditivos. A modelagem deverá evitar vazamento de alvo: campos derivados diretamente do resultado, como `distancia_pactuada_2030_pp` e `status_meta_2030`, não devem ser empregados para prever rótulos derivados desses mesmos campos. Eventos simulados não compõem indicadores oficiais.

### Limitações do protótipo

- O streaming depende de consumo manual em micro-lotes; não há serviço de consumo permanentemente ativo.
- A atualização analítica dos eventos recria as tabelas Silver e Gold.
- A publicação da Gold recria tabelas de resultados; o versionamento histórico integral concentra-se nos snapshots Bronze e na exportação Parquet.
- A análise de alunos utiliza contagens agrupadas e não recalcula taxa amostral ponderada de alfabetização.
- Não foram implementados agendamento automático, CI/CD, infraestrutura como código ou monitoramento gerenciado 24 horas.
- O estudo FinOps é parcial e não substitui a apuração do Cloud Billing.

## 9. Referências

- FIAP — enunciado do *Tech Challenge, Fase 2: Pipeline Híbrido para Análise da Alfabetização no Brasil*.
- [Base dos Dados — Avaliação da Alfabetização](https://basedosdados.org/dataset/073a39d4-89cf-4068-b1e8-34ed0d9c0b72).
- [Documentação BigQuery](https://cloud.google.com/bigquery/docs).
- [Documentação Cloud Storage](https://cloud.google.com/storage/docs).
- [Documentação Pub/Sub](https://cloud.google.com/pubsub/docs).
- [Google Cloud — preços de BigQuery](https://cloud.google.com/bigquery/pricing), [Storage](https://cloud.google.com/storage/pricing) e [Pub/Sub](https://cloud.google.com/pubsub/pricing).
