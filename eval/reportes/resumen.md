# Resultados de evaluación (2026-10-23T18:35:20)

Modelo `qwen3:4b-instruct` · embeddings `bge-m3` · juez `qwen3:8b`

| Métrica | Valor |
|---|---|
| preguntas | 40 |
| recuperacion_acierto_k | 1.0 |
| recuperacion_recall_articulos | 0.971 |
| precision_citas | 0.695 |
| responde_cuando_debe | 1.0 |
| se_abstiene_cuando_debe | 1.0 |
| citas_rechazadas_total | 2 |
| reintentos_total | 0 |
| latencia_p50_s | 4.83 |
| latencia_p95_s | 11.01 |
| tokens_promedio | 1548.25 |
| faithfulness | 0.868 |
| answer_relevancy | 0.993 |
| contextual_precision | 0.934 |
| contextual_recall | 0.971 |
| correctness | 0.697 |

| Tipo | n | Comportamiento correcto |
|---|---|---|
| coloquial | 16 | 1.0 |
| directa | 18 | 1.0 |
| sin_respuesta | 6 | 1.0 |

## Por pregunta

| id | tipo | encontrado | confianza | citados | recall_articulos | faithfulness | answer_relevancy | contextual_precision | contextual_recall | correctness |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | directa | True | alta | ['LFT 76', 'LFT 199'] | 1.0 | 1.0 | 1.0 | 0.85 | 1.0 | 0.6 |
| 2 | directa | True | alta | ['LFT 80'] | 1.0 | 1.0 | 1.0 | 0.58 | 1.0 | 1.0 |
| 3 | coloquial | True | alta | ['LFT 76', 'LFT 78'] | 1.0 | 1.0 | 0.75 | 1.0 | 1.0 | 0.7 |
| 4 | directa | True | alta | ['LFT 81'] | 1.0 | 1.0 | 1.0 | 0.92 | 1.0 | 0.8 |
| 5 | directa | True | alta | ['LFT 87', 'LFT 334 Bis'] | 1.0 | 0.5 | 1.0 | 1.0 | 1.0 | 0.6 |
| 6 | coloquial | True | alta | ['LFT 87', 'LFT 334 Bis'] | 1.0 | 1.0 | 1.0 | 0.83 | 1.0 | 0.4 |
| 7 | coloquial | True | alta | ['LFT 87'] | 1.0 | 0.5 | 1.0 | 1.0 | 1.0 | 0.9 |
| 8 | directa | True | alta | ['LFT 61', 'CPEUM 123', 'LFT 59'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.9 |
| 9 | directa | True | alta | ['CPEUM 123', 'LFT 59'] | 1.0 | 0.0 | 1.0 | 0.97 | 1.0 | 0.7 |
| 10 | coloquial | True | alta | ['LFT 63', 'LFT 423'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.7 |
| 11 | directa | True | alta | ['LFT 66', 'CPEUM 123', 'LFT 68', 'LFT 178'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.7 |
| 12 | coloquial | True | alta | ['LFT 66', 'CPEUM 123', 'LFT 68'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8 |
| 13 | directa | True | alta | ['LFT 71', 'LFT 69', 'LFT 70'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.4 |
| 14 | coloquial | True | alta | ['LFT 71'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8 |
| 15 | coloquial | True | alta | ['LFT 71', 'LFT 73'] | 1.0 | 0.5 | 1.0 | 1.0 | 1.0 | 0.3 |
| 16 | directa | True | alta | ['LFT 74'] | 1.0 | 1.0 | 1.0 | 0.83 | 1.0 | 1.0 |
| 17 | coloquial | True | alta | ['LFT 133', 'LFT 133'] | 1.0 | 0.67 | 1.0 | 1.0 | 1.0 | 0.9 |
| 18 | directa | True | alta | ['LFT 170'] | 1.0 | 1.0 | 1.0 | 0.92 | 1.0 | 0.7 |
| 19 | coloquial | True | media | ['LFT 170'] | 1.0 | 0.5 | 1.0 | 1.0 | 1.0 | 0.8 |
| 20 | coloquial | True | alta | ['LFT 3', 'LFT 56', 'LFT 133', 'LFT 331 Ter'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8 |
| 21 | coloquial | True | alta | ['LFT 132'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.7 |
| 22 | directa | True | alta | ['LFT 48', 'LFT 450', 'LFT 452'] | 1.0 | 0.67 | 1.0 | 0.85 | 1.0 | 0.4 |
| 23 | directa | True | alta | ['LFT 47', 'LFT 47', 'LFT 47'] | 1.0 | 1.0 | 1.0 | 0.41 | 0.0 | 0.3 |
| 24 | coloquial | True | alta | ['LFT 51', 'LFT 48', 'LFT 47'] | 0.5 | 1.0 | 1.0 | 0.95 | 1.0 | 0.6 |
| 25 | directa | True | alta | ['LFT 162', 'LFT 162'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.4 |
| 26 | directa | True | alta | ['LFT 88', 'LFT 89', 'LFT 283'] | 1.0 | 1.0 | 1.0 | 0.7 | 1.0 | 0.8 |
| 27 | coloquial | True | alta | ['LFT 110'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.7 |
| 28 | coloquial | True | alta | ['LFT 330-E'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8 |
| 29 | coloquial | True | alta | ['LFT 330-G', 'LFT 330-E', 'LFT 330-F'] | 1.0 | 0.67 | 1.0 | 1.0 | 1.0 | 0.9 |
| 30 | directa | True | alta | ['LFT 491'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8 |
| 31 | directa | True | alta | ['LFT 487'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8 |
| 32 | directa | True | alta | ['LFT 39-A'] | 1.0 | 0.5 | 1.0 | 1.0 | 1.0 | 0.7 |
| 33 | coloquial | True | alta | ['LFT 22 Bis', 'LFT 174', 'LFT 331 Bis', 'LFT 988', 'LFT 22'] | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.6 |
| 34 | directa | True | alta | ['LFT 153-M', 'LFT 153-A'] | 0.5 | 1.0 | 1.0 | 0.95 | 1.0 | 0.7 |
| 35 | sin_respuesta | False | media | [] |  |  |  |  |  |  |
| 36 | sin_respuesta | False | media | [] |  |  |  |  |  |  |
| 37 | sin_respuesta | False | media | [] |  |  |  |  |  |  |
| 38 | sin_respuesta | False | alta | [] |  |  |  |  |  |  |
| 39 | sin_respuesta | False | alta | [] |  |  |  |  |  |  |
| 40 | sin_respuesta | False | media | [] |  |  |  |  |  |  |
