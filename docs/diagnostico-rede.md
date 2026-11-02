# Diagnóstico de qualidade — Rede do indicador de alfabetização

**Data:** 2026-11-02

## Falha observada

Na primeira execução real do batch, a validação `join_meta_municipio` falhou:

- Universo factual examinado: 23.995 registros de `silver.municipio`;
- Correspondência por `id_municipio` e `ano`: 23.166 registros (~96,54%);
- Correspondência adicionando `rede`: 0 registros (0%);
- Fonte `municipio`: códigos de rede `0`, `2`, `3`, `5`;
- Fonte `meta_alfabetizacao_municipio`: descrição `Municipal`.

A publicação Gold foi bloqueada pela qualidade. O alerta externo não foi entregue porque `ALERT_WEBHOOK_URL` não estava configurado.

## Causa

A Silver normalizava a coluna `rede` como texto, mas não traduzia os códigos. O join comparava categorias numéricas contra descrições textuais. Além disso, o denominador de qualidade incluía redes que não são cobertas pelas metas municipais; a comparação válida depende da mesma rede em ambas as fontes.

## Correção proposta no código

O módulo `rede.py` resolve os códigos **a partir da tabela `silver.dicionario`**, exigindo correspondência unívoca com os códigos presentes na fonte. O join de metas municipais passa a ser avaliado apenas no recorte municipal; para metas estaduais, no recorte da rede pública. A taxa mínima de correspondência permanece em 80%. Dados de outras redes continuam na Gold com metas `NULL` e status `sem_dado`, sem falsificar a associação.

## Validação pendente

A correção foi verificada por testes locais, mas **precisa ser executada no Google Cloud** para confirmar o mapeamento do dicionário real, as taxas por recorte e a não duplicação. Registrar os jobs, as taxas obtidas e as contagens reais de Gold neste documento.

## Correção complementar — escopo de rede Pública

Na primeira execução de `gold-only` após o patch, a rede Municipal foi identificada no dicionário, mas a categoria Pública não existia com correspondência inequívoca em `silver.municipio`. Isso é uma condição válida: metas de UF da rede Pública não devem ser comparadas contra indicadores de município de outra rede.

A nova versão retira essa exigência artificial, deixa os joins de metas municipais restritos à rede Municipal e verifica metas públicas diretamente contra `silver.uf`, no recorte de rede Pública. A Gold municipal não traz mais `meta_uf_2030_percentual`; a comparação estadual é publicada em `gold.indicador_uf` para evitar interpretar a meta pública como uma meta municipal. O código continua exigindo uma tradução inequívoca da rede Pública **em `silver.uf`**, e permanece bloqueante se esse mapeamento oficial não for encontrado.

**Pendente:** validar o código da rede Pública na entidade UF com o dicionário real, executar `gold-only` no GCP, registrar taxa de correspondência e contagens de saída.

## Diagnóstico confirmado pelo dicionário oficial (2026-11-02)

O dicionário em `silver.dicionario` confirmou que as entidades `municipio` e `uf`
usam código `3` para **Municipal**, `5` para **Pública (Estadual e
Municipal)** e `6` para **Pública (Federal, Estadual e Municipal)**. Na
Silver observada, os códigos presentes são `0`, `2`, `3` e `5`.

A correção V2 reconhecia apenas o rótulo exato `Pública` e falhou durante
`gold-only` em `obter_codigos_oficiais`, mesmo existindo a descrição oficial
mais específica. A V3 faz o reconhecimento explícito da abrangência e **não**
considera os códigos 5 e 6 equivalentes. A escolha exige o identificador da
tabela correta, o código presente na Silver e correspondência única. O
limiar de qualidade permanece inalterado (80%).

A tabela `uf` observada tem diferentes coberturas em 2023/2024, então a
validação de joins na GCP deve indicar o denominador e justificar lacunas
territoriais. **A publicação Gold permanece pendente até confirmação da
execução real.**
