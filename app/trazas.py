"""Lee las trazas del Langfuse local (API pública v2) para mostrarlas dentro de la misma página.

Langfuse no se puede incrustar (manda X-Frame-Options: SAMEORIGIN), así que el servidor consulta su API con las
llaves del proyecto —que nunca llegan al navegador— y la interfaz dibuja las etapas con su tiempo, tokens y costo.
"""

import json
import re
from datetime import datetime

import httpx

from app.config import config

ID_VALIDO = re.compile(r"^[0-9a-f]{32}$")
MAX_TEXTO = 4000  # caracteres de entrada/salida que se muestran por etapa
RUIDO_METADATA = ("scope.", "resourceAttributes.")  # atributos de OpenTelemetry que no aportan al lector


class LangfuseNoDisponible(Exception):
    """Langfuse está desactivado, sin llaves o no responde."""


def _cliente() -> httpx.AsyncClient:
    c = config()
    if not (c.langfuse_activo and c.langfuse_public_key and c.langfuse_secret_key):
        raise LangfuseNoDisponible("Langfuse está desactivado (sin llaves o LANGFUSE_ACTIVO=0).")
    return httpx.AsyncClient(base_url=c.langfuse_host, auth=(c.langfuse_public_key, c.langfuse_secret_key), timeout=10)


async def _observaciones(params: dict) -> list[dict]:
    try:
        async with _cliente() as http:
            r = await http.get("/api/public/v2/observations", params=params)
            r.raise_for_status()
            return r.json().get("data", [])
    except httpx.HTTPError as e:
        raise LangfuseNoDisponible(f"Langfuse no respondió ({type(e).__name__}).") from e


def _json(valor):
    if isinstance(valor, str):
        try:
            return json.loads(valor)
        except json.JSONDecodeError:
            return valor
    return valor


def _texto(valor) -> str:
    texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, indent=2)
    return texto if len(texto) <= MAX_TEXTO else texto[:MAX_TEXTO] + "\n… (recortado)"


def _fecha(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


async def listar(limite: int = 30, entorno: str = "") -> list[dict]:
    """Las últimas preguntas (observación raíz `preguntar`), más recientes primero."""
    params = {"name": "preguntar", "limit": min(limite, 100), "fields": "core,basic,io"}
    if entorno:
        params["environment"] = entorno
    filas = []
    for o in sorted(await _observaciones(params), key=lambda o: o["startTime"], reverse=True):
        entrada, salida = _json(o.get("input")) or {}, _json(o.get("output")) or {}
        confianza = salida.get("confianza", {}) if isinstance(salida, dict) else {}
        filas.append({
            "id": o["traceId"],
            "inicio": _fecha(o["startTime"]),
            "latencia_s": o.get("latency"),
            "pregunta": entrada.get("pregunta", "") if isinstance(entrada, dict) else str(entrada),
            "encontrado": salida.get("encontrado_en_documentos") if isinstance(salida, dict) else None,
            "nivel": confianza.get("nivel"),
            "puntaje": confianza.get("puntaje"),
            "entorno": o.get("environment"),
            "advertencia": o.get("level") in ("WARNING", "ERROR"),
        })
    return filas


async def detalle(trace_id: str) -> dict | None:
    """La traza completa: etapas en cascada con tiempos, tokens, costo y su entrada/salida. None si aún no llega."""
    if not ID_VALIDO.match(trace_id):
        raise ValueError("Identificador de traza no válido")
    obs = await _observaciones({"traceId": trace_id, "limit": 100, "fields": "core,basic,model,usage,io,metadata"})
    if not obs:
        return None
    raiz = next((o for o in obs if not o.get("parentObservationId")), obs[0])
    t0, total_ms = _fecha(raiz["startTime"]), max((raiz.get("latency") or 0) * 1000, 1.0)
    padre = {o["id"]: o.get("parentObservationId") for o in obs}

    def profundidad(oid: str) -> int:
        n = 0
        while padre.get(oid):
            oid, n = padre[oid], n + 1
        return n

    # Varias etapas empiezan en el mismo milisegundo: a igual inicio, primero el padre.
    obs.sort(key=lambda o: (o["startTime"], profundidad(o["id"])))

    etapas = []
    for o in obs:
        ms = (o.get("latency") or 0) * 1000
        inicio_ms = (_fecha(o["startTime"]) - t0).total_seconds() * 1000
        uso, costo = o.get("usageDetails") or {}, o.get("totalCost")
        metadata = {k: v for k, v in (_json(o.get("metadata")) or {}).items() if not k.startswith(RUIDO_METADATA)}
        etapas.append({
            "nombre": o["name"], "tipo": o["type"].lower(), "nivel": o.get("level"), "mensaje": o.get("statusMessage"),
            "profundidad": profundidad(o["id"]), "ms": ms,
            "izq_pct": max(min(inicio_ms / total_ms * 100, 99.0), 0.0),
            "ancho_pct": max(min(ms / total_ms * 100, 100.0), 0.8),
            "tokens_entrada": uso.get("input"), "tokens_salida": uso.get("output"), "costo": costo,
            "entrada": _texto(_json(o["input"])) if o.get("input") else None,
            "salida": _texto(_json(o["output"])) if o.get("output") else None,
            "metadata": _texto(metadata) if metadata else None,
            "modelo": o.get("model"),
        })
    entrada, salida = _json(raiz.get("input")) or {}, _json(raiz.get("output")) or {}
    salida = salida if isinstance(salida, dict) else {}
    return {
        "id": trace_id, "entorno": raiz.get("environment"), "total_ms": total_ms,
        "pregunta": entrada.get("pregunta", "") if isinstance(entrada, dict) else str(entrada),
        "respuesta": salida.get("respuesta"), "encontrado": salida.get("encontrado_en_documentos"),
        "confianza": salida.get("confianza") or {},
        "costo_total": sum(e["costo"] or 0 for e in etapas),
        "tokens_total": sum((e["tokens_entrada"] or 0) + (e["tokens_salida"] or 0) for e in etapas),
        "etapas": etapas,
        "url_langfuse": f"{config().langfuse_public_url.rstrip('/')}/project/{config().langfuse_project_id}/traces/{trace_id}",
    }
