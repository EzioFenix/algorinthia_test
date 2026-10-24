"""Lee los reportes que deja `eval/correr_eval.py` para mostrarlos en la pestaña Evaluación."""

import json
import re
from pathlib import Path

from app.config import config

# (clave, nombre, qué mide). El orden es el de las tarjetas en pantalla.
METRICAS_JUEZ = [
    ("faithfulness", "Fidelidad", "¿Lo que afirma está en los fragmentos que usó?"),
    ("answer_relevancy", "Relevancia", "¿Contesta lo que se preguntó?"),
    ("contextual_precision", "Precisión del contexto", "¿Los fragmentos útiles salen primero?"),
    ("contextual_recall", "Cobertura del contexto", "¿Los fragmentos alcanzan para responder?"),
    ("correctness", "Corrección", "¿Coincide con la respuesta esperada?"),
]
METRICAS_PROPIAS = [
    ("recuperacion_acierto_k", "Acierto de recuperación", "Algún artículo esperado llegó al top-6"),
    ("recuperacion_recall_articulos", "Recall de artículos", "Proporción de artículos esperados recuperados"),
    ("precision_citas", "Precisión de citas", "De lo citado, cuánto era lo esperado"),
    ("responde_cuando_debe", "Responde cuando debe", "Hay respuesta en la ley y la da"),
    ("se_abstiene_cuando_debe", "Se abstiene cuando debe", "No hay respuesta y lo dice"),
]
UMBRAL_ALERTA_FIDELIDAD = 0.8
UMBRAL_ALERTA_CORRECCION = 0.6


def _dir() -> Path:
    return config().dir_eval / "reportes"


def _leer(ruta: Path) -> dict | None:
    try:
        return json.loads(ruta.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def ultimo() -> dict | None:
    return _leer(_dir() / "ultimo.json")


NOMBRE_VALIDO = re.compile(r"^[A-Za-z0-9_.-]+$")


def cargar(corrida: str = "") -> dict | None:
    """El reporte pedido por nombre de archivo (sin .json); sin nombre, el último de la corrida principal."""
    if not corrida:
        return ultimo()
    if not NOMBRE_VALIDO.match(corrida) or ".." in corrida:
        return None
    return _leer(_dir() / f"{corrida}.json")


def historial() -> list[dict]:
    """Corridas anteriores (más reciente primero), para ver cómo cambian las métricas entre versiones."""
    corridas = []
    for ruta in _dir().glob("*.json"):
        if ruta.name.startswith("ultimo"):
            continue
        datos = _leer(ruta)
        if datos and "resumen" in datos:
            corridas.append({"archivo": ruta.stem, **datos["resumen"]})
    # Una misma corrida puede estar guardada dos veces (p. ej. copiada como "v1_…"): se conserva la que tiene nombre propio.
    por_fecha: dict[str, dict] = {}
    for c in corridas:
        previa = por_fecha.get(c.get("fecha", ""))
        if previa is None or previa["archivo"].startswith("eval_"):
            por_fecha[c.get("fecha", "")] = c
    return sorted(por_fecha.values(), key=lambda c: c.get("fecha", ""), reverse=True)


def es_ok(f: dict) -> bool:
    """Comportamiento correcto: respondió con lo esperado, o se abstuvo cuando no había respuesta."""
    if not f["articulos_esperados"]:
        return not f["encontrado"]
    return f["encontrado"] and bool(f.get("acierto_recuperacion"))


def en_alerta(f: dict) -> bool:
    fid, cor = f.get("faithfulness"), f.get("correctness")
    return (not es_ok(f)) or (fid is not None and fid < UMBRAL_ALERTA_FIDELIDAD) \
        or (cor is not None and cor < UMBRAL_ALERTA_CORRECCION)


def fila(reporte: dict, pregunta_id: int) -> dict | None:
    return next((f for f in reporte["resultados"] if f["id"] == pregunta_id), None)
