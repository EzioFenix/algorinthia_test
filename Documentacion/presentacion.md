---
marp: true
theme: default
paginate: true
title: Asistente de derechos laborales
---

# Asistente de derechos laborales

**RAG local sobre la LFT y el Art. 123 constitucional**

Python · FastAPI · Ollama (`qwen3:4b-instruct` + `bge-m3`) · SQLite · Langfuse · DeepEval

<!-- Exportar: npx @marp-team/marp-cli Documentacion/presentacion.md --pdf -->

---

## El problema y la decisión clave

- RH recibe decenas de preguntas por semana. **Una respuesta inventada es un riesgo legal.**
- Por eso el diseño gira en torno a una idea: **nada llega al empleado sin estar respaldado y verificado.**
  - Si no hay respaldo → el asistente lo dice explícitamente.
  - Las citas se comprueban contra la base y se muestra el texto oficial, no el del modelo.
  - Cada respuesta trae un **nivel de confianza** calculado con señales medibles.
- Todo corre **local**: los datos de los empleados no salen de la máquina, el costo es $0 y basta con ~4 GB de RAM.

---

## Arquitectura

```
PDF ─► parser legal (artículo / fracción) ─► diff por artículo ─► embeddings (caché) ─► SQLite
                                                                                          │
pregunta ─► glosario + BM25 + embeddings ─► RRF top-6 ─► LLM (JSON forzado) ─► validación de citas
              │ similitud < 0.42 → "no está en los documentos" (sin LLM)       │ 1 reintento
              └──────────── traza Langfuse: busqueda · generacion · validacion ┘
```

- `POST /documentos` → 202 inmediato; un worker procesa cada PDF de forma aislada.
- Reforma de una ley → solo se re-embeben los artículos que cambiaron.

---

## Retos de las respuestas (1–3)

| Reto | Solución |
|---|---|
| Documentos largos | Fragmentos por **artículo y fracción** (2063), con el encabezado como contexto. Solo 6 van al modelo (~1.4k tokens) |
| "¿Me pueden **correr** por estar **embarazada**?" | Embeddings multilingües + **glosario coloquial→legal** + reformulación con LLM solo si hace falta → Art. 133 fr. XV |
| "¿Cuánto es el **salario mínimo** este año?" | Umbral de similitud, opción `no_encontrado` en el esquema, y **sin cita verificada no hay respuesta** → 6/6 abstenciones correctas |

---

## Retos del servicio y la observabilidad (4–6)

- **Validación:** JSON Schema + Pydantic. Cada cita debe **existir**, **haber sido recuperada** y **coincidir** con el texto (fuzzy ≥ 60 %).
  - Atrapó citas reales inventadas: el Art. 5 fuera de contexto y el artículo `"F1"`.
- **Fallos aislados:** un PDF corrupto → `terminado_con_errores`, y los demás terminan.
- **Diagnóstico con Langfuse:** "semanas de incapacidad por maternidad" respondía "no está".
  - `validacion` ✓ y `generacion` ✓, pero `busqueda` traía los arts. 478–496 (riesgos de trabajo).
  - Causa: el glosario expandía *incapacidad*. Corregido → Art. 170 fr. II.

---

## Resultados (40 preguntas: 18 directas, 16 coloquiales, 6 sin respuesta)

| Métrica | v1 | v2 |
|---|---|---|
| Acierto de recuperación @6 | 0.91 | **1.00** |
| Recall de artículos | 0.90 | **0.97** |
| Responde cuando debe / se abstiene cuando debe | 0.94 / 1.00 | **1.00 / 1.00** |
| Precisión de citas | 0.70 | 0.71 |
| Latencia p50 / p95 | 4.0 / 9.4 s | 3.6 / 8.0 s |

**DeepEval (juez `qwen3:8b`, 34 casos con respuesta):**

| Fidelidad | Relevancia | Precisión ctx. | Recall ctx. | Correctness |
|---|---|---|---|---|
| **0.87** | **0.99** | **0.92** | **0.97** | 0.71 |

- Fallos reales que el juez detectó: la respuesta atribuyó a la LFT las 40 horas de la Constitución (#9) y agregó que el aguinaldo "puede variar por acuerdo" (#5).
- Correctness es la métrica más ruidosa: penaliza respuestas válidas a preguntas de lista abierta (#23).

---

## Lo que aprendí del juez

_Pendiente: comparación con la calificación manual (≥15 respuestas)._

---

## Parte 2 · Cáncer de mama

- Clase positiva = **maligno** (en sklearn `target=0` es maligno).
- Split 60/20/20 estratificado; 4 modelos comparados **solo en validación**.
- **Regresión logística**: recall 0.93, AUC 1.00 y 0 falsos positivos en validación. Random Forest y SVM muestran sobreajuste leve.
- Umbral 0.2 elegido en validación. En **prueba**, el recall sube de **0.905 a 0.976** (de 4 malignos no detectados a 1) **con el mismo accuracy (0.965)**: el accuracy no alcanza.

---

## Supuestos y qué haría distinto

- **Supuestos:**
  - solo el Art. 123 de la CPEUM y sin transitorios;
  - el costo por token es de referencia (local = $0);
  - Langfuse Cloud.
- **Puntos débiles:**
  - el modelo **cita de más** (precisión de citas 0.71);
  - el glosario se ajustó con el mismo conjunto de evaluación;
  - el juez local es débil.
- **Con más tiempo:**
  - un conjunto de evaluación apartado;
  - un reranker;
  - transitorios indexados aparte;
  - versiones de la ley por fecha;
  - un A/B formal.
