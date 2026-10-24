"""Búsqueda híbrida: BM25 (FTS5) con glosario + similitud de embeddings, fusionadas con RRF."""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.busqueda.indice import MetaFragmento, indice
from app.busqueda.texto import consulta_fts
from app.db import conexion
from app.ingesta.parser_ley import sin_acentos

CANDIDATOS = 30  # por cada búsqueda antes de fusionar
RRF_K = 60
GARANTIZADOS_DENSOS = 2  # los mejores por significado que siempre entran al top-k (ver `fusionar`)


@dataclass
class Resultado:
    fragmento: MetaFragmento
    rrf: float
    similitud: float
    rango_bm25: int | None
    rango_denso: int | None


@lru_cache
def _glosario() -> list[dict]:
    return json.loads((Path(__file__).parent / "glosario.json").read_text())["entradas"]


def expandir(pregunta: str) -> tuple[str, list[str]]:
    """Agrega términos legales a la consulta según el glosario. Devuelve (consulta, términos agregados)."""
    normal = sin_acentos(pregunta.lower())
    agregados = [
        e["terminos"] for e in _glosario() if any(re.search(r"\b" + re.escape(p), normal) for p in e["patrones"])
    ]
    return " ".join([pregunta, *agregados]), agregados


def _bm25(consulta: str) -> list[int]:
    fts = consulta_fts(consulta)
    if not fts:
        return []
    with conexion() as conn:
        filas = conn.execute(
            "SELECT rowid FROM fragmentos_fts WHERE fragmentos_fts MATCH ? ORDER BY bm25(fragmentos_fts) LIMIT ?",
            (fts, CANDIDATOS),
        ).fetchall()
    return [f[0] for f in filas]


def fusionar(densos: list[int], lexicos: list[int], k: int, garantizados: int = GARANTIZADOS_DENSOS):
    """RRF de las dos listas ordenadas. Los `garantizados` mejores por significado siempre entran al top-k.

    Sin la garantía, un fragmento que solo aparece en la lista semántica (la búsqueda por palabras no lo ve) queda
    por debajo de los que aparecen en ambas, aunque sea el mejor acierto por significado. Caso real: la fracción IV
    del Art. 123 ("cuarenta horas semanales") era la nº 1 por similitud pero quedó fuera del top-6.
    """
    rango_d = {fid: r for r, fid in enumerate(densos, 1)}
    rango_l = {fid: r for r, fid in enumerate(lexicos, 1)}
    puntaje = {
        fid: sum(1 / (RRF_K + r[fid]) for r in (rango_d, rango_l) if fid in r)
        for fid in set(rango_d) | set(rango_l)
    }
    fijos = densos[:garantizados]
    resto = [f for f in sorted(puntaje, key=puntaje.get, reverse=True) if f not in fijos][: max(k - len(fijos), 0)]
    return sorted([*fijos, *resto], key=puntaje.get, reverse=True)[:k], puntaje, rango_d, rango_l


def buscar(consulta_lexica: str, vector: np.ndarray, k: int) -> tuple[list[Resultado], float]:
    """Devuelve los k mejores fragmentos y la similitud máxima (señal absoluta de relevancia)."""
    ids, sims, meta = indice.similitudes(vector)
    if not len(ids):
        return [], 0.0
    sim_por_id = dict(zip(ids.tolist(), sims.tolist(), strict=True))

    top = np.argpartition(-sims, min(CANDIDATOS, len(sims) - 1))[:CANDIDATOS]
    densos = [int(ids[i]) for i in top[np.argsort(-sims[top])]]
    lexicos = [i for i in _bm25(consulta_lexica) if i in meta]

    mejores, puntaje, rango_d, rango_l = fusionar(densos, lexicos, k)
    resultados = [
        Resultado(meta[fid], puntaje[fid], sim_por_id[fid], rango_l.get(fid), rango_d.get(fid)) for fid in mejores
    ]
    return resultados, float(sims.max())
