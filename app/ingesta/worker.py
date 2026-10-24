"""Cola de trabajos en memoria con estado persistido en SQLite.

Un solo worker procesa los trabajos en orden (bajo consumo). Cada PDF se procesa por separado:
si uno falla, los demás siguen y el trabajo termina como "terminado_con_errores".
"""

import asyncio
import json
import logging
import uuid
from pathlib import Path

from app.busqueda.indice import indice
from app.config import config
from app.db import conexion
from app.ingesta.ingesta import ingerir_pdf

log = logging.getLogger(__name__)
_cola: asyncio.Queue[str] = asyncio.Queue()


def crear_trabajo(documentos: list[tuple[str, Path]]) -> str:
    trabajo_id = str(uuid.uuid4())
    with conexion() as conn:
        conn.execute("INSERT INTO trabajos (id, estado) VALUES (?, 'pendiente')", (trabajo_id,))
        conn.executemany(
            "INSERT INTO trabajo_documentos (trabajo_id, nombre, ruta, estado) VALUES (?, ?, ?, 'pendiente')",
            [(trabajo_id, nombre, str(ruta)) for nombre, ruta in documentos],
        )
    _cola.put_nowait(trabajo_id)
    return trabajo_id


def estado_trabajo(trabajo_id: str) -> dict | None:
    with conexion() as conn:
        t = conn.execute("SELECT * FROM trabajos WHERE id = ?", (trabajo_id,)).fetchone()
        if not t:
            return None
        docs = conn.execute(
            "SELECT nombre, estado, error, resumen FROM trabajo_documentos WHERE trabajo_id = ? ORDER BY id",
            (trabajo_id,),
        ).fetchall()
    return {
        "trabajo_id": t["id"],
        "estado": t["estado"],
        "creado": t["creado"],
        "actualizado": t["actualizado"],
        "documentos": [
            {"nombre": d["nombre"], "estado": d["estado"], "error": d["error"],
             "resumen": json.loads(d["resumen"]) if d["resumen"] else None}
            for d in docs
        ],
    }


def trabajos_recientes(limite: int = 8) -> list[dict]:
    with conexion() as conn:
        ids = [r[0] for r in conn.execute("SELECT id FROM trabajos ORDER BY rowid DESC LIMIT ?", (limite,))]
    return [t for t in (estado_trabajo(i) for i in ids) if t]


def _actualizar(sql: str, params: tuple) -> None:
    with conexion() as conn:
        conn.execute(sql, params)


def procesar_trabajo(trabajo_id: str) -> None:
    _actualizar("UPDATE trabajos SET estado='procesando', actualizado=datetime('now') WHERE id=?", (trabajo_id,))
    with conexion() as conn:
        docs = conn.execute(
            "SELECT id, nombre, ruta FROM trabajo_documentos WHERE trabajo_id=? AND estado != 'terminado'",
            (trabajo_id,),
        ).fetchall()

    errores = 0
    for d in docs:
        _actualizar("UPDATE trabajo_documentos SET estado='procesando' WHERE id=?", (d["id"],))
        try:
            resumen = ingerir_pdf(Path(d["ruta"]))
            _actualizar(
                "UPDATE trabajo_documentos SET estado='terminado', error=NULL, resumen=? WHERE id=?",
                (json.dumps(resumen), d["id"]),
            )
            indice.recargar()
            log.info("Documento %s ingerido: %s", d["nombre"], resumen)
        except Exception as e:  # un PDF roto no detiene a los demás
            errores += 1
            log.exception("Falló el documento %s", d["nombre"])
            _actualizar(
                "UPDATE trabajo_documentos SET estado='error', error=? WHERE id=?",
                (f"{type(e).__name__}: {e}"[:500], d["id"]),
            )

    with conexion() as conn:
        fallidos = conn.execute(
            "SELECT COUNT(*) FROM trabajo_documentos WHERE trabajo_id=? AND estado='error'", (trabajo_id,)
        ).fetchone()[0]
    final = "terminado_con_errores" if fallidos else "terminado"
    _actualizar("UPDATE trabajos SET estado=?, actualizado=datetime('now') WHERE id=?", (final, trabajo_id))


async def ciclo_worker() -> None:
    while True:
        trabajo_id = await _cola.get()
        try:
            await asyncio.to_thread(procesar_trabajo, trabajo_id)
        except Exception:
            log.exception("Error inesperado en el trabajo %s", trabajo_id)
            _actualizar(
                "UPDATE trabajos SET estado='terminado_con_errores', actualizado=datetime('now') WHERE id=?",
                (trabajo_id,),
            )
        finally:
            _cola.task_done()


def reencolar_pendientes() -> None:
    """Al arrancar, retoma los trabajos que quedaron a medias por un reinicio."""
    with conexion() as conn:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM trabajos WHERE estado IN ('pendiente', 'procesando') ORDER BY creado")]
    for trabajo_id in ids:
        _cola.put_nowait(trabajo_id)


def ingesta_inicial() -> str | None:
    """Si la base está vacía, encola los PDF oficiales de data/fuentes para que el servicio arranque usable."""
    with conexion() as conn:
        hay_docs = conn.execute("SELECT 1 FROM documentos LIMIT 1").fetchone()
        hay_trabajos = conn.execute("SELECT 1 FROM trabajos LIMIT 1").fetchone()
    pdfs = sorted(config().dir_fuentes.glob("*.pdf"))
    if hay_docs or hay_trabajos or not pdfs:
        return None
    return crear_trabajo([(p.name, p) for p in pdfs])
