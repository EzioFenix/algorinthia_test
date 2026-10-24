# Resultados de evaluación (2026-10-24T00:55:20)

Modelo `qwen3.8:27b-mlx` · embeddings `bge-m3` · juez `qwen3:8b`

| Métrica | Valor |
|---|---|
| preguntas | 40 |
| recuperacion_acierto_k | 0.971 |
| recuperacion_recall_articulos | 0.941 |
| precision_citas | 0.858 |
| responde_cuando_debe | 1.0 |
| se_abstiene_cuando_debe | 0.833 |
| citas_rechazadas_total | 0 |
| reintentos_total | 0 |
| latencia_p50_s | 43.65 |
| latencia_p95_s | 106.0 |
| tokens_promedio | 1426.475 |
| faithfulness | 0.843 |
| answer_relevancy | 0.996 |
| contextual_precision | 0.935 |
| contextual_recall | 0.971 |
| correctness | 0.688 |

| Tipo | n | Comportamiento correcto |
|---|---|---|
| coloquial | 16 | 1.0 |
| directa | 18 | 1.0 |
| sin_respuesta | 6 | 0.833 |

## Por pregunta

| id | tipo | encontrado | confianza | citados | recall_articulos | faithfulness | answer_relevancy | contextual_precision | contextual_recall | correctness |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | directa | True | alta | ['LFT 76'] | 1.0 | 0.5 | 1.0 | 0.85 | 1.0 | 0.7 |
| 2 | directa | True | alta | ['LFT 80'] | 1.0 | 1.0 | 1.0 | 0.58 | 1.0 | 0.7 |
| 3 | coloquial | True | alta | ['LFT 78'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8 |
| 4 | directa | True | alta | ['LFT 81'] | 1.0 | 1.0 | 1.0 | 0.92 | 1.0 | 0.6 |
| 5 | directa | True | alta | ['LFT 87'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8 |
| 6 | coloquial | True | alta | ['LFT 87'] | 1.0 | 0.67 | 1.0 | 0.83 | 1.0 | 0.8 |
| 7 | coloquial | True | alta | ['LFT 87'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8 |
| 8 | directa | True | alta | ['LFT 61', 'CPEUM 123'] | 1.0 | 0.67 | 1.0 | 1.0 | 1.0 | 0.8 |
| 9 | directa | True | alta | ['CPEUM 123'] | 1.0 | 0.5 | 1.0 | 0.97 | 1.0 | 0.7 |
| 10 | coloquial | True | alta | ['LFT 63', 'LFT 64'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8 |
| 11 | directa | True | alta | ['CPEUM 123', 'LFT 66', 'LFT 68'] | 1.0 | 0.67 | 1.0 | 1.0 | 1.0 | 0.9 |
| 12 | coloquial | True | alta | ['LFT 66', 'LFT 68'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.4 |
| 13 | directa | True | alta | ['LFT 69', 'LFT 71'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.4 |
| 14 | coloquial | True | alta | ['LFT 71'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8 |
| 15 | coloquial | True | alta | ['LFT 73'] | 1.0 | 0.67 | 1.0 | 1.0 | 1.0 | 0.7 |
| 16 | directa | True | alta | ['LFT 74'] | 1.0 | 0.5 | 1.0 | 0.83 | 1.0 | 0.8 |
| 17 | coloquial | True | alta | ['LFT 133'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.9 |
| 18 | directa | True | alta | ['LFT 170', 'CPEUM 123'] | 1.0 | 1.0 | 1.0 | 0.92 | 1.0 | 0.3 |
| 19 | coloquial | True | alta | ['LFT 170', 'CPEUM 123'] | 1.0 | 0.33 | 1.0 | 1.0 | 1.0 | 0.7 |
| 20 | coloquial | True | alta | ['LFT 3', 'LFT 56', 'LFT 685 Ter'] | 0.0 | None | 0.86 | 1.0 | 1.0 | 0.8 |
| 21 | coloquial | True | alta | ['LFT 132'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.7 |
| 22 | directa | True | alta | ['LFT 48', 'CPEUM 123'] | 1.0 | 1.0 | 1.0 | 0.89 | 1.0 | 0.3 |
| 23 | directa | True | alta | ['LFT 47', 'LFT 47', 'LFT 47'] | 1.0 | 1.0 | 1.0 | 0.41 | 0.0 | 0.4 |
| 24 | coloquial | True | alta | ['LFT 51', 'LFT 48'] | 0.5 | 1.0 | 1.0 | 0.95 | 1.0 | 0.4 |
| 25 | directa | True | alta | ['LFT 162'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8 |
| 26 | directa | True | alta | ['LFT 88'] | 1.0 | 0.5 | 1.0 | 0.7 | 1.0 | 0.8 |
| 27 | coloquial | True | alta | ['LFT 110'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.3 |
| 28 | coloquial | True | alta | ['LFT 330-E', 'LFT 330-B'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.7 |
| 29 | coloquial | True | alta | ['LFT 330-G'] | 1.0 | 0.67 | 1.0 | 1.0 | 1.0 | 0.8 |
| 30 | directa | True | alta | ['LFT 491', 'LFT 483'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.9 |
| 31 | directa | True | alta | ['LFT 487'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.9 |
| 32 | directa | True | alta | ['LFT 39-A'] | 1.0 | 0.5 | 1.0 | 1.0 | 1.0 | 0.9 |
| 33 | coloquial | True | alta | ['LFT 22', 'LFT 174'] | 1.0 | 0.67 | 1.0 | 1.0 | 1.0 | 0.7 |
| 34 | directa | True | alta | ['LFT 153-A'] | 0.5 | 1.0 | 1.0 | 0.95 | 1.0 | 0.6 |
| 35 | sin_respuesta | False | media | [] |  |  |  |  |  |  |
| 36 | sin_respuesta | False | media | [] |  |  |  |  |  |  |
| 37 | sin_respuesta | False | media | [] |  |  |  |  |  |  |
| 38 | sin_respuesta | False | alta | [] |  |  |  |  |  |  |
| 39 | sin_respuesta | False | alta | [] |  |  |  |  |  |  |
| 40 | sin_respuesta | True | alta | ['LFT 143', 'LFT 102'] |  |  |  |  |  |  |
