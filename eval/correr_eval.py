"""Evaluación del asistente sobre eval/preguntas.json. Proceso aparte: nunca corre dentro de /preguntar.

Uso:
    uv run python -m eval.correr_eval                 # métricas propias + DeepEval (juez local)
    uv run python -m eval.correr_eval --sin-juez      # solo métricas deterministas (rápido)
    uv run python -m eval.correr_eval --limite 5      # primeras 5 preguntas
"""

import argparse
import asyncio
import json
import os
import statistics
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
# El juez local tarda decenas de segundos por llamada: los timeouts de DeepEval (pensados para APIs) lo cortan.
os.environ.setdefault("DEEPEVAL_DISABLE_TIMEOUTS", "1")
# Las trazas de la evaluación quedan separadas de las del uso real en Langfuse.
os.environ.setdefault("LANGFUSE_TRACING_ENVIRONMENT", "evaluacion")

import httpx

from app.asistente import responder
from app.busqueda.indice import indice
from app.config import config
from app.db import inicializar
from app.ingesta.ingesta import ingerir_pdf
from app.observabilidad import vaciar
from eval import calificacion

DIR = Path(__file__).parent
DIR_REPORTES = DIR / "reportes"


def usar_salida(carpeta: str) -> None:
    """Escribe los reportes en otra carpeta (para experimentos que no deben reemplazar el reporte oficial)."""
    global DIR_REPORTES
    DIR_REPORTES = Path(carpeta)
METRICAS_JUEZ = ["faithfulness", "answer_relevancy", "contextual_precision", "contextual_recall", "correctness"]


def clave_articulo(ley: str, articulo: str) -> str:
    return f"{ley} {articulo}"


async def correr_asistente(preguntas: list[dict]) -> list[dict]:
    filas = []
    async with httpx.AsyncClient() as http:
        for p in preguntas:
            inicio = time.perf_counter()
            r, d = await responder(http, p["pregunta"])
            recuperados = [clave_articulo(x.fragmento.ley, x.fragmento.articulo) for x in d.fragmentos]
            citados = [clave_articulo(c["ley"], c["articulo"]) for c in r["citas"]]
            esperados = p["articulos_esperados"]
            fila = {
                **p,
                "respuesta": r["respuesta"],
                "encontrado": r["encontrado_en_documentos"],
                "confianza": r["confianza"]["nivel"],
                "confianza_puntaje": r["confianza"]["puntaje"],
                "citados": citados,
                "recuperados": recuperados,
                "contexto": [f"{x.fragmento.etiqueta}: {x.fragmento.texto}" for x in d.fragmentos],
                "citas_rechazadas": len(d.rechazadas),
                "reintentos": d.reintentos,
                "reescrita": d.consulta_reescrita,
                "similitud_max": round(d.similitud_max, 3),
                "tokens_entrada": d.tokens_entrada,
                "tokens_salida": d.tokens_salida,
                "segundos": round(time.perf_counter() - inicio, 2),
                "trace_id": r["trace_id"],
            }
            if esperados:
                fila["recall_articulos"] = len(set(esperados) & set(recuperados)) / len(esperados)
                fila["acierto_recuperacion"] = bool(set(esperados) & set(recuperados))
                fila["precision_citas"] = (
                    len([c for c in citados if c in esperados]) / len(citados) if citados else None
                )
            fila["abstencion_correcta"] = fila["encontrado"] == bool(esperados)
            filas.append(fila)
            print(f"[{p['id']:>2}] {'✓' if fila['abstencion_correcta'] else '✗'} {fila['segundos']:>5}s "
                  f"citados={citados} esperados={esperados}  {p['pregunta'][:60]}")
    return filas


def correr_juez(filas: list[dict]) -> None:
    """DeepEval sobre las preguntas con respuesta en los documentos. Agrega los puntajes a cada fila."""
    from deepeval import evaluate
    from deepeval.evaluate.configs import AsyncConfig, DisplayConfig, ErrorConfig
    from deepeval.metrics import (
        AnswerRelevancyMetric,
        ContextualPrecisionMetric,
        ContextualRecallMetric,
        FaithfulnessMetric,
        GEval,
    )
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams

    from eval.juez import JuezOllama

    juez = JuezOllama()
    metricas = {
        "faithfulness": FaithfulnessMetric(model=juez, include_reason=True, async_mode=False),
        "answer_relevancy": AnswerRelevancyMetric(model=juez, include_reason=True, async_mode=False),
        "contextual_precision": ContextualPrecisionMetric(model=juez, include_reason=True, async_mode=False),
        "contextual_recall": ContextualRecallMetric(model=juez, include_reason=True, async_mode=False),
        "correctness": GEval(
            name="Correctness",
            model=juez,
            evaluation_steps=[
                "Compara la respuesta real con la respuesta esperada.",
                "Penaliza fuertemente datos que contradigan a la respuesta esperada (días, porcentajes, plazos).",
                "Omitir detalles secundarios es aceptable si lo esencial coincide.",
            ],
            evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
            async_mode=False,
        ),
    }
    evaluables = [f for f in filas if f["articulos_esperados"]]
    casos = [
        LLMTestCase(
            input=f["pregunta"],
            actual_output=f["respuesta"],
            expected_output=f["respuesta_esperada"],
            retrieval_context=f["contexto"] or ["(sin fragmentos)"],
            name=str(f["id"]),
        )
        for f in evaluables
    ]
    print(f"\nDeepEval: {len(casos)} casos × {len(metricas)} métricas con juez {juez.get_model_name()}…")
    resultado = evaluate(
        test_cases=casos,
        metrics=list(metricas.values()),
        async_config=AsyncConfig(run_async=False),  # una llamada al juez a la vez: bajo consumo
        display_config=DisplayConfig(print_results=False, show_indicator=True),
        error_config=ErrorConfig(ignore_errors=True),  # un caso fallido no tumba la corrida; se reporta abajo
    )
    por_id = {f["id"]: f for f in evaluables}
    nombres = {m.__name__ if hasattr(m, "__name__") else m.name: k for k, m in metricas.items()}
    for tr in resultado.test_results:
        fila = por_id[int(tr.name)]
        for md in tr.metrics_data or []:
            clave = next((k for n, k in nombres.items() if n.lower().startswith(md.name.lower().split(" [")[0])), None)
            clave = clave or md.name.lower().replace(" ", "_")
            fila[clave] = md.score
            fila[f"{clave}_razon"] = md.reason
    sin_puntaje = [f["id"] for f in evaluables if any(f.get(m) is None for m in METRICAS_JUEZ)]
    if sin_puntaje:
        print(f"⚠ {len(sin_puntaje)} casos sin todas las métricas del juez: {sin_puntaje}")


def promedio(valores: list) -> float | None:
    v = [x for x in valores if x is not None]
    return round(statistics.mean(v), 3) if v else None


def resumen(filas: list[dict], con_juez: bool, etiqueta: str = "") -> dict:
    con_resp = [f for f in filas if f["articulos_esperados"]]
    sin_resp = [f for f in filas if not f["articulos_esperados"]]
    tiempos = sorted(f["segundos"] for f in filas)
    r = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "modelo": config().llm_model,
        "etiqueta": etiqueta,
        "embeddings": config().embed_model,
        "juez": config().judge_model if con_juez else None,
        "preguntas": len(filas),
        "recuperacion_acierto_k": promedio([float(f["acierto_recuperacion"]) for f in con_resp]),
        "recuperacion_recall_articulos": promedio([f["recall_articulos"] for f in con_resp]),
        "precision_citas": promedio([f["precision_citas"] for f in con_resp]),
        "responde_cuando_debe": promedio([float(f["encontrado"]) for f in con_resp]),
        "se_abstiene_cuando_debe": promedio([float(not f["encontrado"]) for f in sin_resp]),
        "citas_rechazadas_total": sum(f["citas_rechazadas"] for f in filas),
        "reintentos_total": sum(f["reintentos"] for f in filas),
        "latencia_p50_s": tiempos[len(tiempos) // 2] if tiempos else None,
        "latencia_p95_s": tiempos[min(len(tiempos) - 1, int(len(tiempos) * 0.95))] if tiempos else None,
        "tokens_promedio": promedio([f["tokens_entrada"] + f["tokens_salida"] for f in filas]),
    }
    if con_juez:
        for m in METRICAS_JUEZ:
            r[m] = promedio([f.get(m) for f in con_resp])
    por_tipo = {}
    for tipo in sorted({f["tipo"] for f in filas}):
        grupo = [f for f in filas if f["tipo"] == tipo]
        por_tipo[tipo] = {"n": len(grupo), "comportamiento_correcto": promedio([float(f["abstencion_correcta"]) for f in grupo])}
    r["por_tipo"] = por_tipo
    return r


def escribir_reportes(filas: list[dict], res: dict, con_juez: bool, etiqueta: str = "") -> Path:
    """Con `etiqueta` (p. ej. "max") la corrida es una variante: se guarda aparte y NO reemplaza el reporte principal
    (`ultimo.json`) ni crea la plantilla de calificación manual, que pertenece a la corrida principal."""
    DIR_REPORTES.mkdir(exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    sufijo = f"_{etiqueta}" if etiqueta else ""
    ruta = DIR_REPORTES / f"eval_{sello}{sufijo}.json"
    ruta.write_text(json.dumps({"resumen": res, "resultados": filas}, ensure_ascii=False, indent=2))
    (DIR_REPORTES / f"ultimo{sufijo}.json").write_text(ruta.read_text())

    lineas = [f"# Resultados de evaluación ({res['fecha']})", "",
              f"Modelo `{res['modelo']}` · embeddings `{res['embeddings']}` · juez `{res['juez']}`", "",
              "| Métrica | Valor |", "|---|---|"]
    lineas += [f"| {k} | {v} |" for k, v in res.items() if k not in {"fecha", "modelo", "etiqueta", "embeddings", "juez", "por_tipo"}]
    lineas += ["", "| Tipo | n | Comportamiento correcto |", "|---|---|---|"]
    lineas += [f"| {t} | {v['n']} | {v['comportamiento_correcto']} |" for t, v in res["por_tipo"].items()]
    cols = ["id", "tipo", "encontrado", "confianza", "citados", "recall_articulos"] + (METRICAS_JUEZ if con_juez else [])
    lineas += ["", "## Por pregunta", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for f in filas:
        lineas.append("| " + " | ".join(
            str(round(f.get(c), 2) if isinstance(f.get(c), float) else f.get(c, "")) for c in cols) + " |")
    (DIR_REPORTES / f"resumen{sufijo}.md").write_text("\n".join(lineas) + "\n")

    # Plantilla para la calificación manual (≥15). No sobrescribe una calificación existente.
    if con_juez and not etiqueta:
        calificacion.asegurar(filas, res["fecha"])
    return ruta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sin-juez", action="store_true", help="omite DeepEval (solo métricas deterministas)")
    parser.add_argument("--limite", type=int, default=None, help="evalúa solo las primeras N preguntas")
    parser.add_argument("--etiqueta", default="", help="nombre de una variante (p. ej. max): se guarda aparte del reporte principal")
    parser.add_argument("--salida", default=None, help="carpeta donde escribir los reportes (por defecto eval/reportes)")
    args = parser.parse_args()
    if args.salida:
        usar_salida(args.salida)

    inicializar()
    indice.recargar()
    if not len(indice):
        # Un solo comando: si nadie ha levantado el servicio, se ingieren los PDF oficiales aquí mismo.
        pdfs = sorted(config().dir_fuentes.glob("*.pdf"))
        if not pdfs:
            raise SystemExit(f"La base está vacía y no hay PDF en {config().dir_fuentes}")
        print(f"Base vacía: ingiriendo {len(pdfs)} PDF de data/fuentes (una sola vez)…")
        for pdf in pdfs:
            print(" ", ingerir_pdf(pdf))
        indice.recargar()
    preguntas = json.loads((DIR / "preguntas.json").read_text())[: args.limite]

    filas = asyncio.run(correr_asistente(preguntas))
    vaciar()
    error_juez = None
    if not args.sin_juez:
        try:
            correr_juez(filas)
        except Exception as e:  # noqa: BLE001 — si el juez falla no se pierden las respuestas ya generadas
            error_juez = e
            print(f"\n✗ El juez falló ({type(e).__name__}: {e}). Se guarda el reporte sin sus métricas.")
    con_juez = not args.sin_juez and error_juez is None
    res = resumen(filas, con_juez, args.etiqueta)
    ruta = escribir_reportes(filas, res, con_juez, args.etiqueta)
    print("\n" + json.dumps(res, ensure_ascii=False, indent=2))
    print(f"\nReporte: {ruta}  ·  {DIR_REPORTES / 'resumen.md'}")
    if error_juez:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
