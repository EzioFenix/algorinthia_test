"""Rutas JSON del servicio: /documentos, /trabajo/{id}, /preguntar."""

import secrets
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

from app.asistente import responder
from app.config import config
from app.db import conexion
from app.ingesta.worker import crear_trabajo, estado_trabajo

router = APIRouter()
MAGIC_PDF = b"%PDF-"
BLOQUE = 1 << 20


def verificar_api_key(x_api_key: str | None = Header(default=None)) -> None:
    esperada = config().api_key
    if esperada and not secrets.compare_digest(x_api_key or "", esperada):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key inválida o ausente (encabezado X-API-Key)")


class LimitePorIP:
    """Rate limit simple en memoria (ventana deslizante). Suficiente para un solo proceso."""

    def __init__(self, maximo: int, ventana_s: float) -> None:
        self.maximo, self.ventana = maximo, ventana_s
        self.historial: dict[str, deque] = defaultdict(deque)

    def __call__(self, request: Request) -> None:
        ip = request.client.host if request.client else "?"
        ahora, cola = time.monotonic(), self.historial[ip]
        while cola and ahora - cola[0] > self.ventana:
            cola.popleft()
        if len(cola) >= self.maximo:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiadas preguntas; espera un momento")
        cola.append(ahora)


limite_preguntas = LimitePorIP(maximo=20, ventana_s=60)


async def guardar_pdfs(archivos: list[UploadFile]) -> list[tuple[str, Path]]:
    """Valida tamaño, cantidad y que sean PDF reales; los guarda con nombre UUID (nunca el del cliente)."""
    c = config()
    if not archivos:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Envía al menos un PDF en el campo 'archivos'")
    if len(archivos) > c.max_pdfs_por_trabajo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Máximo {c.max_pdfs_por_trabajo} PDF por trabajo")

    c.dir_subidas.mkdir(parents=True, exist_ok=True)
    guardados = []
    limite = c.max_pdf_mb * BLOQUE
    for archivo in archivos:
        nombre = (archivo.filename or "documento.pdf")[:200]
        destino = c.dir_subidas / f"{uuid.uuid4()}.pdf"
        tamano, inicio = 0, b""
        with open(destino, "wb") as f:
            while bloque := await archivo.read(BLOQUE):
                if not inicio:
                    inicio = bloque[:5]
                tamano += len(bloque)
                if tamano > limite:
                    break
                f.write(bloque)
        if tamano > limite or inicio != MAGIC_PDF:
            destino.unlink(missing_ok=True)
            for _, ruta in guardados:
                ruta.unlink(missing_ok=True)
            motivo = f"supera {c.max_pdf_mb} MB" if tamano > limite else "no es un PDF válido"
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{nombre}' {motivo}")
        guardados.append((nombre, destino))
    return guardados


class PreguntaIn(BaseModel):
    pregunta: str = Field(min_length=3, max_length=1000, examples=["¿Me pueden correr por estar embarazada?"])


class CitaOut(BaseModel):
    ley: str
    articulo: str
    apartado: str | None
    fraccion: str | None
    texto: str


class ConfianzaOut(BaseModel):
    nivel: str
    puntaje: float | None
    motivos: list[str]


class RespuestaOut(BaseModel):
    respuesta: str
    encontrado_en_documentos: bool
    citas: list[CitaOut]
    confianza: ConfianzaOut
    trace_id: str | None
    trace_url: str | None


@router.post("/documentos", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(verificar_api_key)])
async def subir_documentos(archivos: list[UploadFile] = File(...)) -> dict:
    """Recibe uno o varios PDF y devuelve de inmediato el id del trabajo; el procesamiento sigue en segundo plano."""
    guardados = await guardar_pdfs(archivos)
    trabajo_id = crear_trabajo(guardados)
    return {"trabajo_id": trabajo_id, "estado": "pendiente", "documentos": [n for n, _ in guardados]}


@router.get("/trabajo/{trabajo_id}", dependencies=[Depends(verificar_api_key)])
async def consultar_trabajo(trabajo_id: uuid.UUID) -> dict:
    estado = estado_trabajo(str(trabajo_id))
    if not estado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trabajo no encontrado")
    return estado


@router.post("/preguntar", response_model=RespuestaOut,
             dependencies=[Depends(verificar_api_key), Depends(limite_preguntas)])
async def preguntar(entrada: PreguntaIn, request: Request) -> dict:
    resultado, _ = await responder(request.app.state.http, entrada.pregunta.strip())
    return resultado


@router.get("/documentos", dependencies=[Depends(verificar_api_key)])
async def listar_documentos() -> list[dict]:
    with conexion() as conn:
        filas = conn.execute(
            "SELECT d.clave, d.nombre, d.version_dof, d.actualizado,"
            " (SELECT COUNT(*) FROM articulos a WHERE a.documento_id = d.id) AS articulos,"
            " (SELECT COUNT(*) FROM fragmentos f WHERE f.documento_id = d.id) AS fragmentos"
            " FROM documentos d ORDER BY d.clave"
        ).fetchall()
    return [dict(f) for f in filas]
