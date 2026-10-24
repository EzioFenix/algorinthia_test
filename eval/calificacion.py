"""Calificación manual (eval/calificacion_manual.csv) y su comparación con el juez de DeepEval.

La persona califica 0 (mal), 0.5 (parcial) o 1 (bien) dos cosas por respuesta:
    humano_correcta_0a1  ↔  juez_correctness   (¿contesta bien, según la respuesta esperada?)
    humano_fiel_0a1      ↔  juez_faithfulness  (¿lo que afirma está en los fragmentos?)
"""

import csv
import os
import tempfile
import threading
from pathlib import Path

from app.config import config

COLUMNAS = ["id", "pregunta", "respuesta", "citados", "juez_correctness", "juez_faithfulness",
            "humano_correcta_0a1", "humano_fiel_0a1", "comentario", "corrida"]
PARES = [("humano_correcta_0a1", "juez_correctness", "Corrección"), ("humano_fiel_0a1", "juez_faithfulness", "Fidelidad")]
UMBRAL = 0.5   # el juez "aprueba" con puntaje ≥ 0.5 (umbral por defecto de DeepEval)
MINIMO = 15    # el enunciado pide calificar al menos 15 respuestas
_candado = threading.Lock()


def ruta() -> Path:
    return config().dir_eval / "calificacion_manual.csv"


def numero(valor) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _segura(celda: str) -> str:
    """Evita que Excel interprete texto libre como fórmula (CSV injection)."""
    celda = celda.strip()[:500]
    return "'" + celda if celda[:1] in ("=", "+", "-", "@", "\t", "\r") else celda


def _escribir(filas: list[dict]) -> None:
    destino = ruta()
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=destino.parent, suffix=".csv")
    with os.fdopen(fd, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNAS)
        w.writeheader()
        w.writerows(filas)
    os.replace(tmp, destino)  # escritura atómica: nunca queda un CSV a medias


def asegurar(resultados: list[dict], corrida: str = "") -> None:
    """Crea la plantilla desde un reporte de evaluación. No sobrescribe una calificación existente.

    `corrida` (la fecha del reporte) liga la calificación a ESA corrida: las respuestas y los puntajes del juez del CSV
    son los de ese reporte, así que solo allí tiene sentido calificar y comparar."""
    with _candado:
        if ruta().exists():
            return
        _escribir([
            {"id": f["id"], "pregunta": f["pregunta"], "respuesta": f["respuesta"], "citados": " ; ".join(f["citados"]),
             "juez_correctness": f.get("correctness"), "juez_faithfulness": f.get("faithfulness"),
             "humano_correcta_0a1": "", "humano_fiel_0a1": "", "comentario": "", "corrida": corrida}
            for f in resultados if f["articulos_esperados"]
        ])


def cargar() -> dict[int, dict]:
    if not ruta().exists():
        return {}
    with open(ruta(), newline="") as fh:
        return {int(f["id"]): f for f in csv.DictReader(fh)}


def corrida_csv() -> str | None:
    """La corrida a la que pertenece la calificación manual; None si todavía no existe el archivo."""
    filas = cargar()
    return None if not filas else next(iter(filas.values())).get("corrida") or ""


def guardar(pregunta_id: int, correcta: float, fiel: float | None, comentario: str) -> None:
    for valor in (correcta, fiel):
        if valor is not None and not 0 <= valor <= 1:
            raise ValueError("Las calificaciones van de 0 a 1")
    with _candado:
        filas = list(cargar().values())
        fila = next((f for f in filas if int(f["id"]) == pregunta_id), None)
        if fila is None:
            raise KeyError(pregunta_id)
        fila["humano_correcta_0a1"] = correcta
        fila["humano_fiel_0a1"] = "" if fiel is None else fiel
        fila["comentario"] = _segura(comentario)
        _escribir(filas)


def acuerdo(filas: dict[int, dict]) -> dict:
    """Compara a la persona con el juez: porcentaje de acuerdo aprueba/reprueba y lista de discrepancias."""
    resumen = {"calificadas": sum(1 for f in filas.values() if numero(f["humano_correcta_0a1"]) is not None),
               "minimo": MINIMO, "metricas": []}
    for col_humano, col_juez, nombre in PARES:
        pares = [(f, numero(f[col_humano]), numero(f[col_juez])) for f in filas.values()]
        pares = [(f, h, j) for f, h, j in pares if h is not None and j is not None]
        if not pares:
            continue
        coinciden = [(h >= UMBRAL) == (j >= UMBRAL) for _, h, j in pares]
        resumen["metricas"].append({
            "nombre": nombre,
            "n": len(pares),
            "acuerdos": sum(coinciden),
            "porcentaje": sum(coinciden) / len(pares),
            "diferencia_media": sum(abs(h - j) for _, h, j in pares) / len(pares),
            "juez_mas_estricto": sum(1 for _, h, j in pares if h >= UMBRAL > j),
            "juez_mas_laxo": sum(1 for _, h, j in pares if j >= UMBRAL > h),
            "discrepancias": [
                {"id": int(f["id"]), "pregunta": f["pregunta"], "humano": h, "juez": j, "comentario": f["comentario"]}
                for (f, h, j), ok in zip(pares, coinciden, strict=True) if not ok
            ],
        })
    return resumen
