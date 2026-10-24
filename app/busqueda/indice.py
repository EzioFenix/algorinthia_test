"""Índice denso en memoria: todos los embeddings en una matriz numpy (≈2k × 1024 floats ≈ 8 MB)."""

import threading
from dataclasses import dataclass

import numpy as np

from app.db import conexion


@dataclass(frozen=True)
class MetaFragmento:
    id: int
    ley: str
    nombre_ley: str
    articulo: str
    apartado: str | None
    fraccion: str | None
    ruta: str
    texto: str

    @property
    def etiqueta(self) -> str:
        partes = [f"{self.ley} Art. {self.articulo}"]
        if self.apartado:
            partes.append(f"apartado {self.apartado}")
        if self.fraccion:
            partes.append(f"fracc. {self.fraccion}")
        return ", ".join(partes)


class Indice:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.ids = np.empty(0, dtype=np.int64)
        self.matriz = np.empty((0, 0), dtype=np.float32)
        self.meta: dict[int, MetaFragmento] = {}

    def recargar(self) -> None:
        with conexion() as conn:
            filas = conn.execute(
                "SELECT f.id, d.clave, d.nombre, f.articulo, f.apartado, f.fraccion, f.ruta, f.texto, f.embedding"
                " FROM fragmentos f JOIN documentos d ON d.id = f.documento_id ORDER BY f.id"
            ).fetchall()
        ids = np.array([f["id"] for f in filas], dtype=np.int64)
        matriz = (
            np.vstack([np.frombuffer(f["embedding"], dtype=np.float32) for f in filas])
            if filas else np.empty((0, 0), dtype=np.float32)
        )
        meta = {
            f["id"]: MetaFragmento(f["id"], f["clave"], f["nombre"], f["articulo"], f["apartado"], f["fraccion"], f["ruta"], f["texto"])
            for f in filas
        }
        with self._lock:  # intercambio atómico: las búsquedas en curso usan la versión anterior
            self.ids, self.matriz, self.meta = ids, matriz, meta

    def similitudes(self, vector: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[int, MetaFragmento]]:
        with self._lock:
            ids, matriz, meta = self.ids, self.matriz, self.meta
        if not len(ids):
            return ids, np.empty(0, dtype=np.float32), meta
        return ids, matriz @ vector, meta

    def __len__(self) -> int:
        return len(self.ids)


indice = Indice()
