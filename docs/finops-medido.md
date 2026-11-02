# FinOps — Pipeline Híbrido para Análise da Alfabetização no Brasil

**Tech Challenge FIAP — Fase 2**  
**Ambiente:** Google Cloud Platform (GCP)  
**Projeto GCP:** `project-69677cc7-ad0d-49e4-b6f`  
**Bucket:** `gs://fiap-projeto_fase2_entrega/`  
**Referência das medições:** 02/11/2026  
**Moeda dos preços de referência:** dólar americano (USD)

> **Escopo e interpretação:** os volumes abaixo foram medidos no ambiente GCP do projeto. Os valores monetários são **projeções brutas**, antes das franquias gratuitas e dos créditos promocionais, **não uma fatura efetivamente cobrada**. Onde não houve medição suficiente, a lacuna é explicitada. Valores arredondados não devem ser interpretados como custos exatos.

## 1. Objetivo

Demonstrar o consumo de recursos da arquitetura híbrida **Batch + Streaming** com **Bronze, Silver e Gold**, justificar decisões de engenharia de dados e estimar seu custo mensal em produção com base em medições reais e premissas explícitas.

A arquitetura utiliza **BigQuery** (consultas, armazenamento analítico, tabelas de operação), **Cloud Storage** (histórico de snapshots Parquet e exportação da Gold) e **Pub/Sub** (eventos de streaming simulados). A recepção de alertas é feita por um webhook do Slack.

## 2. Medições realizadas

### 2.1 BigQuery — armazenamento

O levantamento foi realizado por meio da biblioteca Python `google-cloud-bigquery`, listando tabelas dos datasets e somando `num_bytes` das tabelas nativas. Essa medida é uma **aproximação de tamanho lógico das tabelas nativas**, não uma medição completa de bytes faturados ou do espaço físico interno. As tabelas externas Bronze apontam para objetos armazenados no Cloud Storage.

| Dataset | Tabelas encontradas | Armazenamento medido (GiB) |
|---|---:|---:|
| `bronze` | 8 | 0,000001 |
| `silver` | 9 | 0,337129 |
| `gold` | 6 | 0,002291 |
| `ops` | 5 | 0,000018 |
| **Total BigQuery** | **28** | **0,339439** |

Equivalência aproximada: **347,59 MiB**.

**Limitação da medição:** a consulta a `region-us.INFORMATION_SCHEMA.TABLE_STORAGE_BY_PROJECT` retornou `Access Denied`. Por esse motivo, foi utilizada a API Python para obter metadados das tabelas. O levantamento não substitui a conferência da cobrança real no Cloud Billing nem contempla com precisão *time travel*, retenção física ou demais particularidades da modalidade de armazenamento.

### 2.2 Cloud Storage — armazenamento

Comando executado:

```bash
gcloud storage du --summarize gs://fiap-projeto_fase2_entrega/
```

Saída medida:

```text
204451589    gs://fiap-projeto_fase2_entrega
```

| Indicador | Valor |
|---|---:|
| Bytes armazenados | **204.451.589 bytes** |
| Tamanho em MiB | **194,98 MiB** |
| Tamanho em GiB | **0,190410 GiB** |

Os arquivos incluem o histórico de ingestão e a exportação Parquet da Gold para a Fase 3. Essa é a ocupação **no momento da coleta**, não a ocupação média ou final de um mês.

**Localização do bucket: ainda não confirmada na evidência recebida.** Antes de encerrar a entrega, executar:

```bash
gcloud storage buckets describe \
  gs://fiap-projeto_fase2_entrega \
  --format="yaml(location,storageClass)"
```

O script de provisionamento do projeto foi preparado para usar `us-central1` por padrão, mas a existência da configuração no código **não comprova** a localização do bucket já criado.

### 2.3 Processamento BigQuery

O pipeline registra bytes processados e duração de etapas em `ops.metricas`. O comando `python -m alfabetizacao.cli finops` retornou, na medição original:

```text
Medição salva em docs/finops-medido.md; custo parcial bruto US$ 0.018234/mês
```

Esse subtotal **já abrangia consultas BigQuery e armazenamento Cloud Storage**, com uma cadência assumida de **4 execuções Batch por mês**, mas **não incluía o armazenamento BigQuery**. O valor refletia o snapshot do bucket existente no momento da execução original do comando; o tamanho do bucket foi medido novamente depois.

Para a tabela econômica consolidada, utiliza-se uma **aproximação de US$ 0,01443/mês para as consultas**, consistente com a decomposição anterior do relatório. O valor exato por execução não foi transcrito para este documento; deve ser revalidado a partir de `ops.metricas` ou do JSON auxiliar `docs/finops-medido.json` antes de ser apresentado como medição exata.

**Histórico técnico confirmado:** o Batch completo terminou com `SUCESSO` em 02/11/2026, `run_id=20261102T213746Z_f9941625`, após aproximadamente 86 segundos. O projeto já havia validado 23.995 registros nas camadas Silver e Gold, com zero duplicações na chave analítica consultada.

### 2.4 Streaming Pub/Sub

Evidência de testes executados:

| Indicador | Resultado observado |
|---|---:|
| Mensagens registradas na Bronze | 7 |
| Eventos únicos válidos na Gold | 5 |
| Duplicações na Gold | 0 |
| Eventos inválidos colocados em quarentena | 1 |
| Latência média dos 5 eventos válidos | 18,538 segundos |

Os eventos foram identificados como `origem=simulado` e `categoria_fonte=nao_oficial`. **Não há, nesta medição, contagem de bytes efetivamente cobrados por publicação e entrega de mensagens**. Por isso, não se atribui custo monetário exato ao Pub/Sub. Para projeção de escala, adota-se apenas a premissa operacional de **300 mensagens/mês (10/dia)**.

## 3. Premissas e preços unitários

| Item | Premissa adotada | Referência |
|---|---|---|
| Consultas BigQuery sob demanda | **US$ 6,25/TiB** adicional | [Tabela oficial BigQuery](https://cloud.google.com/bigquery/pricing) |
| BigQuery — armazenamento lógico ativo | **aprox. US$ 0,023/GiB-mês** | [Tabela oficial BigQuery](https://cloud.google.com/bigquery/pricing) |
| Cloud Storage Standard regional (cenário `us-central1`) | **aprox. US$ 0,020/GiB-mês** | [Tabela oficial Cloud Storage](https://cloud.google.com/storage/pricing) |
| Cloud Storage Standard multirregional (cenário `US`) | **aprox. US$ 0,026/GiB-mês** | [Tabela oficial Cloud Storage](https://cloud.google.com/storage/pricing) |
| Pub/Sub | Cobrança por bytes publicados, entregues e possivelmente armazenados; 10 GiB/mês de throughput básico gratuito | [Tabela oficial Pub/Sub](https://cloud.google.com/pubsub/pricing) |
| Periodicidade Batch | **4 execuções/mês** | Premissa de produção, não observação de quatro execuções mensais recorrentes |
| Frequência de streaming | **300 mensagens/mês** | Premissa de produção, não métrica faturável medida |
| Tamanho inicial dos dados | Medições acima, após as execuções do desafio | Evidências do ambiente GCP |

Os preços são referências em USD, sujeitos a região, classe de armazenamento, modalidade contratada, variação de preços e regras da conta de faturamento. A situação real da cobrança deve ser verificada no **Cloud Billing**, em moeda configurada na conta.

## 4. Estimativa mensal bruta — cenário de pequeno porte

**Cenário-base:** quatro Batches/mês, mantendo **constante** o estoque de dados medido; consultas sob demanda; armazenamento lógico ativo BigQuery; Cloud Storage Standard regional em `us-central1`. Trata-se de uma fotografia inicial **sem crescimento acumulado dos snapshots**.

| Serviço | Unidade | Quantidade medida / projetada | Preço unitário | Custo bruto mensal estimado |
|---|---|---:|---:|---:|
| BigQuery — consultas | TiB processados/mês | Aproximação derivada do FinOps inicial, com 4 Batches/mês | US$ 6,25/TiB | **US$ 0,01443** (aprox.) |
| BigQuery — armazenamento lógico ativo | GiB-mês | **0,339439 GiB**, medido | US$ 0,023/GiB-mês | **US$ 0,00781** |
| Cloud Storage Standard regional | GiB-mês | **0,190410 GiB**, medido | US$ 0,020/GiB-mês | **US$ 0,00381** |
| Pub/Sub — publicação/entrega | GiB de throughput | **Não medido em bytes**; cenário de 300 mensagens/mês | Franquia e tarifa conforme tipo de operação | **Não quantificado** |
| Cloud Storage — operações | Operações de leitura/escrita | **Não medidas** | Conforme classe/região | **Não quantificado** |
| Transferência de dados/egress | GiB transferidos | **Não medidos** | Conforme origem/destino | **Não quantificado** |
| **Subtotal bruto de itens quantificados** | | | | **US$ 0,02605/mês** |

**Variação de localização:** caso a localização efetiva do bucket seja `US` (multirregião) e a classe permaneça Standard, sua parcela de armazenamento passa a aproximadamente **US$ 0,00495/mês**, e o subtotal bruto estimado dos itens quantificados passa a aproximadamente **US$ 0,02719/mês**. A localização **precisa ser confirmada** antes da escolha do cenário final.

**Reconciliação com o relatório original:** o comando `finops` havia produzido **US$ 0,018234/mês** como subtotal parcial de consultas + Cloud Storage. A presente consolidação adiciona **aproximadamente US$ 0,00781/mês** de armazenamento BigQuery, totalizando **aproximadamente US$ 0,02604/mês** com aquele subtotal anterior. A tabela acima usa a **medição de Cloud Storage mais recente** e uma parcela de consultas arredondada, resultando em **US$ 0,02605/mês**. As diferenças decorrem da data da medição e do arredondamento; **não são duas cobranças adicionais**.

**Atenção:** a projeção não inclui todos os serviços nem simula crescimento indefinido da Bronze. Logo, não representa um orçamento fechado de produção.

### 4.1 Custo após franquias gratuitas e créditos

- **BigQuery:** a franquia de referência é de **1 TiB de consultas por mês e 10 GiB de armazenamento por mês**, compartilhada conforme regras da conta de faturamento. O volume medido do projeto está abaixo dessas franquias, **mas isso não comprova custo zero se a conta tiver outros consumos**.
- **Cloud Storage:** existem **5 GB-mês gratuitos** para Standard em regiões elegíveis (`us-west1`, `us-central1`, `us-east1`), sujeitos às regras e ao consumo agregado. A região exata do bucket ainda depende de confirmação.
- **Pub/Sub:** os primeiros **10 GiB/mês do throughput básico** podem estar cobertos pela franquia; falta medir os bytes dos eventos.
- **Créditos promocionais:** o usuário informou possuir créditos de teste disponíveis. Eles não devem ser confundidos com uma tarifa de US$ 0 ou com o benefício gratuito permanente.

**Conclusão financeira provisória:** a arquitetura mostrou baixíssimo consumo de armazenamento e processamento no ensaio acadêmico. **Não é possível afirmar uma fatura mensal de US$ 0 sem conferir o Cloud Billing e a localização do bucket.**

## 5. Boas práticas FinOps implementadas e propostas

| Prática | Situação | Benefício / observação |
|---|---|---|
| Arquivos Parquet na Bronze | Implementado | Reduz volume armazenado e facilita leitura seletiva |
| Histórico de snapshots Bronze | Implementado | Rastreabilidade, com custo de armazenamento crescente entre execuções |
| `dry-run` antes de ingestão Batch | Implementado | Estima bytes a processar antes da execução real |
| `MAX_BYTES_BILLED=1073741824` | Configurado no projeto | Limita cobrança por consulta que respeite esse parâmetro, não o custo total mensal |
| Integração Silver/Gold com regras bloqueantes | Implementado | Reduz retrabalho decorrente de dados incompatíveis |
| Métricas de execução em `ops.metricas` | Implementado | Permite acompanhar bytes e duração por etapa |
| Slack via webhook em falhas | Comprovado | Alerta externo sem monitoramento manual contínuo |
| Processamento incremental analítico de eventos | Melhoria futura | O consumidor processa mensagens em micro-lotes, mas a atualização analítica ainda pode reler histórico |
| Retenção configurável de snapshots e revisão periódica de uso | Melhoria futura | Concilia preservação histórica e custo de longo prazo |
| Orçamentos e alertas de faturamento no Console | A verificar | Alertas de orçamento **não interrompem automaticamente** o consumo |

## 6. Evidências e rastreabilidade

Arquivos que devem acompanhar a documentação, após revisão para não publicar credenciais:

- `docs/evidencias/01_execucoes.json`: histórico de execuções;
- `docs/evidencias/02_metricas.json`: métricas de processamento e latência;
- `docs/evidencias/03_qualidade.json`: verificações e bloqueios de qualidade;
- `docs/evidencias/04_alertas.json`: histórico de alertas;
- `docs/evidencias/05_gold_municipio.json`: amostra analítica;
- `docs/evidencias/06_gold_eventos.json`: amostra dos eventos;
- `docs/evidencias/08_batch_completo_sucesso.log`: execução Batch completa;
- `docs/evidencias/14_alerta_slack.png`: notificação confirmada no canal Slack;
- `docs/evidencias/15_armazenamento_bigquery.txt`: medição por API Python, caso salva no repositório;
- `docs/finops-medido.json`: registro auxiliar dos valores do comando FinOps, caso exportado.

**Identificador do Batch completo:** `20261102T213746Z_f9941625` — **SUCESSO**.  
**Exportação da Gold para Fase 3:** `gs://fiap-projeto_fase2_entrega/gold/indicador_municipio/run_id=20261102T220143Z_f35fc64a/part-*.parquet`.  
**Job de exportação:** `bdf79cb6-ebcd-4226-8322-abf4d187be0f`.

Os nomes dos arquivos de evidência listados representam a organização prevista/gerada pelo projeto; confirme sua presença e versione apenas os arquivos pertinentes. Este documento não contém tokens ou URLs secretas de webhook.

## 7. Comandos de revalidação

```bash
# Região e classe do bucket
gcloud storage buckets describe gs://fiap-projeto_fase2_entrega \
  --format="yaml(location,storageClass)"

# Tamanho atual do bucket
gcloud storage du --summarize gs://fiap-projeto_fase2_entrega/

# Execuções e métricas persistidas
PROJECT=$(gcloud config get-value project)
bq query --location=US --use_legacy_sql=false "
SELECT run_id, SUM(COALESCE(bytes_processados,0)) AS bytes_processados
FROM \`${PROJECT}.ops.metricas\`
WHERE etapa LIKE 'bronze-%' OR etapa LIKE 'silver-%' OR etapa LIKE 'gold-%'
GROUP BY run_id
ORDER BY run_id DESC
LIMIT 10
"
```

**Não execute `python -m alfabetizacao.cli finops` depois de editar este documento sem antes salvar uma cópia:** no código atual, esse comando **regera/sobrescreve** o arquivo `docs/finops-medido.md` com seu modelo simplificado, removendo os complementos manuais.

## 8. Limitações e próximos passos

1. Confirmar a **localização e a classe real** dos objetos Cloud Storage; somente então consolidar o cenário regional ou multirregional.
2. Conferir o detalhamento dos **bytes por execução** e reconciliar o subtotal de consultas com `ops.metricas` / `docs/finops-medido.json`.
3. Medir o **throughput Pub/Sub em bytes** e as operações de Cloud Storage, sem converter número de mensagens diretamente em volume faturável.
4. Obter o custo realizado no **Cloud Billing** (período, moeda, SKUs e créditos) e separar custo bruto de cobrança líquida.
5. Estimar o crescimento mensal da Bronze mantendo o histórico, e definir retenção e cadência operacional em produção.
6. Validar regionalidade de processamento, transferência de saída e eventuais diferenças de preço entre regiões.

## 9. Fontes oficiais de preço

- [Google Cloud — BigQuery Pricing](https://cloud.google.com/bigquery/pricing)
- [Google Cloud — Cloud Storage Pricing](https://cloud.google.com/storage/pricing)
- [Google Cloud — Pub/Sub Pricing](https://cloud.google.com/pubsub/pricing)
- [Google Cloud — Cloud Billing](https://console.cloud.google.com/billing)

---

*Documento de medição e estimativa preparado para a entrega acadêmica da FIAP. O custo bruto dos itens quantificados não substitui a conciliação com o faturamento do Google Cloud.*
