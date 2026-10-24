"""Punto de entrada: `uvicorn app.main:app`."""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import observabilidad, ui
from app.api.rutas import router
from app.busqueda.indice import indice
from app.db import inicializar
from app.ingesta.worker import ciclo_worker, ingesta_inicial, reencolar_pendientes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("app")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    inicializar()
    indice.recargar()
    reencolar_pendientes()
    if trabajo := ingesta_inicial():
        log.info("Base vacía: ingiriendo data/fuentes (trabajo %s)", trabajo)
    worker = asyncio.create_task(ciclo_worker())
    app.state.http = httpx.AsyncClient()
    yield
    worker.cancel()
    await app.state.http.aclose()
    observabilidad.vaciar()


app = FastAPI(
    title="Asistente de derechos laborales",
    description="Responde preguntas con la Ley Federal del Trabajo y el Art. 123 constitucional, citando artículos.",
    version="0.1.0",
    lifespan=ciclo_de_vida,
)
app.include_router(router)
app.include_router(ui.router)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    respuesta = await call_next(request)
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    return respuesta


@app.exception_handler(Exception)
async def error_generico(request: Request, exc: Exception):
    """Nunca se devuelve el stack trace; el id permite encontrarlo en los logs."""
    error_id = uuid.uuid4().hex[:8]
    log.exception("Error %s en %s %s", error_id, request.method, request.url.path)
    return JSONResponse({"detail": "Error interno", "error_id": error_id}, status_code=500)


@app.get("/salud")
async def salud() -> dict:
    return {"estado": "ok", "fragmentos_indexados": len(indice)}
