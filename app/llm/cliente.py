"""Cliente mínimo de la API de Ollama: embeddings y chat con salida estructurada."""

import time
from dataclasses import dataclass

import httpx
import numpy as np

from app.config import config


@dataclass
class RespuestaLLM:
    contenido: str
    tokens_entrada: int
    tokens_salida: int
    segundos: float


@dataclass
class Embeddings:
    vectores: np.ndarray  # (n, d) normalizados a norma 1
    tokens: int


def _normalizar(vectores: list[list[float]]) -> np.ndarray:
    m = np.asarray(vectores, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True).clip(min=1e-12)


def embeber(textos: list[str]) -> Embeddings:
    """Síncrono: lo usa el worker de ingesta (en un hilo)."""
    c = config()
    r = httpx.post(
        f"{c.ollama_base_url}/api/embed",
        json={"model": c.embed_model, "input": textos},
        timeout=c.llm_timeout_s * 3,
    )
    r.raise_for_status()
    datos = r.json()
    return Embeddings(_normalizar(datos["embeddings"]), datos.get("prompt_eval_count", 0))


async def aembeber(cliente: httpx.AsyncClient, texto: str) -> Embeddings:
    c = config()
    r = await cliente.post(
        f"{c.ollama_base_url}/api/embed",
        json={"model": c.embed_model, "input": [texto]},
        timeout=c.llm_timeout_s,
    )
    r.raise_for_status()
    datos = r.json()
    return Embeddings(_normalizar(datos["embeddings"]), datos.get("prompt_eval_count", 0))


async def achat(cliente: httpx.AsyncClient, mensajes: list[dict], esquema: dict | None = None) -> RespuestaLLM:
    c = config()
    cuerpo = {
        "model": c.llm_model,
        "messages": mensajes,
        "stream": False,
        "think": False,  # Qwen3: sin razonamiento visible, mucho más rápido
        "keep_alive": c.llm_keep_alive,
        # num_predict acota la salida: sin tope, un modelo pequeño puede repetir texto hasta el timeout
        "options": {"temperature": c.llm_temperature, "num_ctx": c.llm_num_ctx, "num_predict": c.llm_max_tokens,
                    "repeat_penalty": 1.05},
    }
    if esquema:
        cuerpo["format"] = esquema
    inicio = time.perf_counter()
    r = await cliente.post(f"{c.ollama_base_url}/api/chat", json=cuerpo, timeout=c.llm_timeout_s)
    r.raise_for_status()
    datos = r.json()
    return RespuestaLLM(
        contenido=datos["message"]["content"],
        tokens_entrada=datos.get("prompt_eval_count", 0),
        tokens_salida=datos.get("eval_count", 0),
        segundos=time.perf_counter() - inicio,
    )


def costo_usd(tokens_entrada: int, tokens_salida: int) -> dict[str, float]:
    c = config()
    entrada = tokens_entrada * c.costo_entrada_usd_mtok / 1e6
    salida = tokens_salida * c.costo_salida_usd_mtok / 1e6
    return {"input": entrada, "output": salida, "total": entrada + salida}
