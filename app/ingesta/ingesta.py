"""Ingesta de una ley: parseo, diff por artículo contra la versión guardada y embeddings solo de lo nuevo."""

import hashlib
import json
import logging
from pathlib import Path

import numpy as np

from app.busqueda.texto import para_indice
from app.config import config
from app.db import conexion
from app.ingesta.parser_ley import Fragmento, extraer_paginas, fragmentar, parsear_ley, sha256_texto
from app.llm.cliente import embeber

log = logging.getLogger(__name__)
LOTE_EMBEDDINGS = 32


def sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def texto_para_embedding(nombre_ley: str, f: Fragmento, clave: str) -> str:
    return f"{nombre_ley} — {f.ruta}\n{f.etiqueta(clave)}\n{f.texto}"


def _embeddings_con_cache(textos: list[str]) -> list[bytes]:
    """Devuelve un embedding por texto; solo llama a Ollama para los que no están en caché."""
    modelo = config().embed_model
    hashes = [sha256_texto(t) for t in textos]
    with conexion() as conn:
        filas = conn.execute(
            "SELECT hash, vector FROM cache_embeddings WHERE modelo = ? AND hash IN (SELECT value FROM json_each(?))",
            (modelo, json.dumps(hashes)),
        ).fetchall()
    cache = {f["hash"]: f["vector"] for f in filas}
    faltan = [i for i, h in enumerate(hashes) if h not in cache]
    for inicio in range(0, len(faltan), LOTE_EMBEDDINGS):
        lote = faltan[inicio : inicio + LOTE_EMBEDDINGS]
        vectores = embeber([textos[i] for i in lote]).vectores
        with conexion() as conn:
            for i, v in zip(lote, vectores, strict=True):
                blob = v.astype(np.float32).tobytes()
                cache[hashes[i]] = blob
                conn.execute(
                    "INSERT OR REPLACE INTO cache_embeddings (hash, modelo, vector) VALUES (?, ?, ?)",
                    (hashes[i], modelo, blob),
                )
    log.info("Embeddings: %d en caché, %d calculados", len(textos) - len(faltan), len(faltan))
    return [cache[h] for h in hashes]


def ingerir_pdf(ruta: Path) -> dict:
    sha = sha256_archivo(ruta)
    ley = parsear_ley(extraer_paginas(ruta, config().max_paginas_pdf))
    if not ley.articulos:
        raise ValueError("No se encontraron artículos: el PDF no parece una ley de la Cámara de Diputados")

    with conexion() as conn:
        doc = conn.execute("SELECT id, sha256 FROM documentos WHERE clave = ?", (ley.clave,)).fetchone()
        if doc and doc["sha256"] == sha:
            return {"ley": ley.clave, "version_dof": ley.version_dof, "sin_cambios": True}
        previos = (
            {r["articulo"]: r["hash"] for r in conn.execute(
                "SELECT articulo, hash FROM articulos WHERE documento_id = ?", (doc["id"],))}
            if doc else {}
        )

    actuales = {a.numero: a for a in ley.articulos}
    hashes = {n: sha256_texto(a.texto) for n, a in actuales.items()}
    nuevos = [n for n in actuales if n not in previos]
    modificados = [n for n in actuales if n in previos and previos[n] != hashes[n]]
    eliminados = [n for n in previos if n not in actuales]
    a_procesar = nuevos + modificados

    fragmentos = [f for n in a_procesar for f in fragmentar(actuales[n])]
    vectores = _embeddings_con_cache([texto_para_embedding(ley.nombre, f, ley.clave) for f in fragmentos])

    with conexion() as conn:
        if doc:
            documento_id = doc["id"]
            conn.execute(
                "UPDATE documentos SET nombre=?, version_dof=?, sha256=?, actualizado=datetime('now') WHERE id=?",
                (ley.nombre, ley.version_dof, sha, documento_id),
            )
        else:
            documento_id = conn.execute(
                "INSERT INTO documentos (clave, nombre, version_dof, sha256) VALUES (?, ?, ?, ?)",
                (ley.clave, ley.nombre, ley.version_dof, sha),
            ).lastrowid

        for n in modificados + eliminados:
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM fragmentos WHERE documento_id=? AND articulo=?", (documento_id, n))]
            conn.executemany("DELETE FROM fragmentos_fts WHERE rowid=?", [(i,) for i in ids])
            conn.execute("DELETE FROM fragmentos WHERE documento_id=? AND articulo=?", (documento_id, n))
        conn.executemany(
            "DELETE FROM articulos WHERE documento_id=? AND articulo=?", [(documento_id, n) for n in eliminados]
        )
        conn.executemany(
            "INSERT OR REPLACE INTO articulos (documento_id, articulo, texto, hash) VALUES (?, ?, ?, ?)",
            [(documento_id, n, actuales[n].texto, hashes[n]) for n in a_procesar],
        )
        for f, vector in zip(fragmentos, vectores, strict=True):
            fid = conn.execute(
                "INSERT INTO fragmentos (documento_id, articulo, apartado, fraccion, ruta, texto, hash, embedding)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (documento_id, f.articulo, f.apartado, f.fraccion, f.ruta, f.texto, f.hash, vector),
            ).lastrowid
            conn.execute(
                "INSERT INTO fragmentos_fts (rowid, texto) VALUES (?, ?)",
                (fid, para_indice(f"{f.etiqueta(ley.clave)} {f.ruta} {f.texto}")),
            )

    return {
        "ley": ley.clave,
        "version_dof": ley.version_dof,
        "articulos_nuevos": len(nuevos),
        "articulos_modificados": len(modificados),
        "articulos_eliminados": len(eliminados),
        "articulos_sin_cambios": len(actuales) - len(a_procesar),
        "fragmentos_indexados": len(fragmentos),
    }
