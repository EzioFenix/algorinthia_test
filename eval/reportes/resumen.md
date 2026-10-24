# Resultados de evaluación (2026-10-23T14:22:16)

Modelo `qwen3:4b-instruct` · embeddings `bge-m3` · juez `qwen3:8b`

| Métrica | Valor |
|---|---|
| preguntas | 40 |
| recuperacion_acierto_k | 1.0 |
| recuperacion_recall_articulos | 0.971 |
| precision_citas | 0.68 |
| responde_cuando_debe | 1.0 |
| se_abstiene_cuando_debe | 1.0 |
| citas_rechazadas_total | 2 |
| reintentos_total | 0 |
| latencia_p50_s | 3.76 |
| latencia_p95_s | 9.24 |
| tokens_promedio | 1551.275 |
| faithfulness | 0.873 |
| answer_relevancy | 0.993 |
| contextual_precision | 0.92 |
| contextual_recall | 0.971 |
| correctness | 0.712 |

| Tipo | n | Comportamiento correcto |
|---|---|---|
| coloquial | 16 | 1.0 |
| directa | 18 | 1.0 |
| sin_respuesta | 6 | 1.0 |

## Por pregunta

| id | tipo | encontrado | confianza | citados | recall_articulos | faithfulness | answer_relevancy | contextual_precision | contextual_recall | correctness |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | directa | True | alta | ['LFT 76', 'LFT 199'] | 1.0 | 1.0 | 1.0 | 0.85 | 1.0 | 0.6 |
| 2 | directa | True | alta | ['LFT 80'] | 1.0 | 1.0 | 1.0 | 0.58 | 1.0 | 0.9 |
| 3 | coloquial | True | alta | ['LFT 76', 'LFT 77', 'LFT 199', 'LFT 179', 'LFT 233'] | 1.0 | 0.67 | 0.75 | 1.0 | 1.0 | 0.5 |
| 4 | directa | True | alta | ['LFT 81'] | 1.0 | 1.0 | 1.0 | 0.92 | 1.0 | 0.9 |
| 5 | directa | True | alta | ['LFT 87', 'LFT 334 Bis'] | 1.0 | 0.5 | 1.0 | 1.0 | 1.0 | 0.6 |
| 6 | coloquial | True | alta | ['LFT 87', 'LFT 334 Bis'] | 1.0 | 1.0 | 1.0 | 0.83 | 1.0 | 0.5 |
| 7 | coloquial | True | alta | ['LFT 87'] | 1.0 | 0.5 | 1.0 | 1.0 | 1.0 | 0.6 |
| 8 | directa | True | alta | ['LFT 61', 'CPEUM 123', 'LFT 59'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.9 |
| 9 | directa | True | alta | ['LFT 59', 'CPEUM 123'] | 1.0 | 0.5 | 1.0 | 1.0 | 1.0 | 0.8 |
| 10 | coloquial | True | alta | ['LFT 63', 'LFT 423'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.7 |
| 11 | directa | True | alta | ['LFT 66', 'CPEUM 123', 'LFT 68', 'CPEUM 123'] | 1.0 | 1.0 | 1.0 | 0.95 | 1.0 | 0.7 |
| 12 | coloquial | True | alta | ['LFT 66', 'CPEUM 123', 'LFT 68'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8 |
| 13 | directa | True | alta | ['LFT 69', 'LFT 336'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.7 |
| 14 | coloquial | True | alta | ['LFT 71'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8 |
| 15 | coloquial | True | alta | ['LFT 71', 'LFT 73'] | 1.0 | 0.5 | 1.0 | 1.0 | 1.0 | 0.6 |
| 16 | directa | True | alta | ['LFT 74'] | 1.0 | 1.0 | 1.0 | 0.83 | 1.0 | 1.0 |
| 17 | coloquial | True | alta | ['LFT 170', 'LFT 170', 'LFT 133', 'LFT 47'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.9 |
| 18 | directa | True | alta | ['LFT 170'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.7 |
| 19 | coloquial | True | media | ['LFT 170'] | 1.0 | 0.5 | 1.0 | 1.0 | 1.0 | 0.7 |
| 20 | coloquial | True | alta | ['LFT 133', 'LFT 331 Ter'] | 1.0 | 1.0 | 1.0 | 0.92 | 1.0 | 0.8 |
| 21 | coloquial | True | alta | ['LFT 132'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.6 |
| 22 | directa | True | alta | ['LFT 48', 'LFT 450'] | 1.0 | 1.0 | 1.0 | 0.67 | 1.0 | 0.6 |
| 23 | directa | True | alta | ['LFT 47', 'LFT 47', 'LFT 47'] | 1.0 | 1.0 | 1.0 | 0.41 | 0.0 | 0.2 |
| 24 | coloquial | True | alta | ['LFT 51', 'LFT 48', 'LFT 47'] | 0.5 | 1.0 | 1.0 | 0.95 | 1.0 | 0.7 |
| 25 | directa | True | alta | ['LFT 162'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.7 |
| 26 | directa | True | alta | ['LFT 88', 'LFT 89', 'LFT 283'] | 1.0 | 1.0 | 1.0 | 0.7 | 1.0 | 0.8 |
| 27 | coloquial | True | alta | ['LFT 110'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.7 |
| 28 | coloquial | True | alta | ['LFT 330-E'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.7 |
| 29 | coloquial | True | alta | ['LFT 330-G', 'LFT 330-E'] | 1.0 | 0.5 | 1.0 | 0.7 | 1.0 | 0.7 |
| 30 | directa | True | alta | ['LFT 491'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.9 |
| 31 | directa | True | alta | ['LFT 487'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8 |
| 32 | directa | True | alta | ['LFT 39-A'] | 1.0 | 0.5 | 1.0 | 1.0 | 1.0 | 0.7 |
| 33 | coloquial | True | alta | ['LFT 22 Bis', 'LFT 174', 'LFT 331 Bis', 'LFT 988', 'LFT 22'] | 1.0 | 0.5 | 1.0 | 1.0 | 1.0 | 0.7 |
| 34 | directa | True | alta | ['LFT 153-M', 'LFT 153-A'] | 0.5 | 1.0 | 1.0 | 0.95 | 1.0 | 0.7 |
| 35 | sin_respuesta | False | media | [] |  |  |  |  |  |  |
| 36 | sin_respuesta | False | media | [] |  |  |  |  |  |  |
| 37 | sin_respuesta | False | media | [] |  |  |  |  |  |  |
| 38 | sin_respuesta | False | alta | [] |  |  |  |  |  |  |
| 39 | sin_respuesta | False | alta | [] |  |  |  |  |  |  |
| 40 | sin_respuesta | False | media | [] |  |  |  |  |  |  |
