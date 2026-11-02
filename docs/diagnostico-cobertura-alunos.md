# Investigação: cobertura entre indicadores municipais e microdados de alunos

## Resultado observado no Google Cloud (2026-11-02)

A execução V3 falhou com **12.408/23.995 = 51,71%** no join completo de município, ano, rede e série. Após consultar as tabelas Silver, observou-se:

| Ano | Rede | Série | Registros municipais | Correspondentes | Taxa |
| --- | --- | --- | ---: | ---: | ---: |
| 2023 | 2 (Estadual) | 2 | 1.149 | 1.054 | 91,73% |
| 2023 | 3 (Municipal) | 2 | 5.448 | 4.821 | 88,49% |
| 2023 | 5 (Pública = Estadual + Municipal) | 2 | 4.950 | 0 | 0% |
| 2024 | 0 (Total) | 2 | 398 | 0 | 0% |
| 2024 | 2 (Estadual) | 2 | 1.086 | 1.085 | 99,91% |
| 2024 | 3 (Municipal) | 2 | 5.448 | 5.448 | 100% |
| 2024 | 5 (Pública = Estadual + Municipal) | 2 | 5.516 | 0 | 0% |

Os significados das redes foram verificados na tabela oficial `silver.dicionario`: os registros individuais de `alunos` possuem redes 1–4; a tabela `municipio` tem também redes agregadas 0 (Total) e 5 (Pública Estadual e Municipal). Portanto, comparar diretamente `_rede=5` com microdados `_rede=2/3` **não é um join válido**. A V4 só filtrava por ano e não corrigia essa incompatibilidade de granularidade.

## Ajuste V5

- `join_alunos_cobertura_historica`: indicador **INFORMATIVO**, sobre todas as 23.995 linhas. Esperado: 12.408 / 23.995 = **51,71%**.
- `join_alunos_redes_individuais`: **BLOQUEANTE** com limiar de 80%. Universo: redes individuais conforme `silver.dicionario` para a tabela `alunos`, e pares ano/série presentes na fonte. Pelos dados observados: 12.408 / 13.131 = **94,49%**.
- `join_alunos_ano_{ano}_rede_{rede}_serie_{serie}`: regras **BLOQUEANTES** para cada segmento do universo comparável, evitando que um grupo de baixa qualidade seja escondido pela média global.
- Linhas de redes 0/5 continuam no indicador Gold oficial. `total_registros_alunos` nessas linhas permanece `NULL` no join direto. **NULL não significa zero alunos**.
- **Não reconstruímos** indicadores agregados de redes 0/5 a partir dos microdados neste patch. Isso exigiria uma agregação distinta, com o universo de avaliados, os pesos amostrais, a flag de alfabetizado e a definição de rede correspondente; essa reconciliação pode ser diferencial adicional do desafio.

## Como repetir a avaliação

Executar `python -m alfabetizacao.cli gold-only` após os testes. Os logs reais e as saídas do BigQuery devem ser coletados no diretório `docs/evidencias/` para posterior publicação seletiva no GitHub.

**Ressalva:** as taxas de match não demonstram equivalência entre o indicador oficial publicado e uma taxa recalculada de microdados. O indicador de alfabetização deve ser ponderado e ter denominador de alunos avaliados, não de todos os registros.
