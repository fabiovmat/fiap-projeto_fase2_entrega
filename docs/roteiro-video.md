# Roteiro do vídeo executivo (até 5 minutos)

**0:00–0:40 — problema**: Compromisso Nacional Criança Alfabetizada; percentual de alunos acima do ponto de corte de 743. Diferenciar aspiração de universalização e meta pactuada da fonte (rede Pública: 80 em 2030).

**0:40–1:40 — arquitetura**: mostrar diagrama no README; Base dos Dados/BigQuery → export histórico imutável Parquet GCS (Bronze) → BigQuery Silver (normalização) → BigQuery Gold. Demonstração de eventos Pub/Sub, identificação clara `origem='simulado'`.

**1:40–2:45 — demonstração com evidências**: mostrar os jobs reais BigQuery (IDs), tabelas Gold e objetos GCS. Navegar no console Pub/Sub; publicar dois eventos e duplicata; observar deduplicação e latência na Gold. Não misturar indicadores oficiais com simulados.

**2:45–3:35 — qualidade/monitoramento**: executar demonstração bloqueante; exibir `ops.qualidade`, `ops.metricas`, alertas persistidos. Mostrar notificação externa se webhook tiver sido configurado.

**3:35–4:20 — FinOps**: apresentar o resultado de `docs/finops-medido.md`, com bytes reais e projeção mensal. Explicar BigQuery dry-run, histórico Parquet e custos adicionais ainda não medidos.

**4:20–5:00 — valor e IA**: explicar acompanhamento de desigualdade regional e futuros modelos preditivos por município; evitar leakage do alvo. Encerrar com limites do protótipo e link GitHub.

> Substituir as referências gerais por números **realmente medidos** na sua execução. O vídeo precisa ser gravado por integrante e disponibilizado por URL no README.
