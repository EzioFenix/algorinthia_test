"""Cada prueba usa una base SQLite temporal; nada toca data/asistente.db ni llama a Ollama."""

import numpy as np
import pytest

from app.config import config
from app.db import inicializar


@pytest.fixture(autouse=True)
def base_temporal(tmp_path, monkeypatch):
    monkeypatch.setattr(config(), "db_path", tmp_path / "prueba.db")
    monkeypatch.setattr(config(), "dir_subidas", tmp_path / "subidas")
    monkeypatch.setattr(config(), "dir_fuentes", tmp_path / "fuentes")
    monkeypatch.setattr(config(), "dir_eval", tmp_path / "eval")
    # Hermético: las pruebas no deben depender del .env real (llaves de Langfuse, API_KEY, etc.)
    for campo in ("langfuse_public_key", "langfuse_secret_key", "api_key"):
        monkeypatch.setattr(config(), campo, "")
    inicializar()
    yield


@pytest.fixture
def embeddings_falsos(monkeypatch):
    """Sustituye a Ollama: vector determinista por texto y cuenta cuántos textos se embebieron."""
    from app.ingesta import ingesta
    from app.llm.cliente import Embeddings

    llamadas = []

    def falso(textos):
        llamadas.extend(textos)
        vectores = np.array([np.random.default_rng(abs(hash(t)) % 2**32).random(8) for t in textos], dtype=np.float32)
        return Embeddings(vectores / np.linalg.norm(vectores, axis=1, keepdims=True), 0)

    monkeypatch.setattr(ingesta, "embeber", falso)
    return llamadas


def _resultado(id, tipo, esperados, **extra):
    base = {
        "id": id, "tipo": tipo, "categoria": "vacaciones", "pregunta": f"Pregunta {id} de prueba",
        "respuesta_esperada": "esperada", "articulos_esperados": esperados, "respuesta": "respuesta del asistente",
        "encontrado": bool(esperados), "confianza": "alta", "confianza_puntaje": 0.9,
        "citados": esperados[:], "recuperados": esperados[:] + ["LFT 99"], "contexto": [], "citas_rechazadas": 0,
        "reintentos": 0, "reescrita": None, "similitud_max": 0.6, "tokens_entrada": 100, "tokens_salida": 50,
        "segundos": 3.2, "trace_id": None, "abstencion_correcta": True,
    }
    if esperados:
        base.update(recall_articulos=1.0, acierto_recuperacion=True, precision_citas=1.0)
    return {**base, **extra}


@pytest.fixture
def reporte(tmp_path):
    """Un reporte de evaluación mínimo en el directorio temporal de eval."""
    import json

    resultados = [
        _resultado(1, "directa", ["LFT 76"], faithfulness=0.5, faithfulness_razon="razón del juez", correctness=0.9,
                   answer_relevancy=1.0, contextual_precision=1.0, contextual_recall=1.0),
        _resultado(2, "sin_respuesta", [], encontrado=False),
    ]
    resumen = {
        "fecha": "2026-10-23T14:22:16", "modelo": "qwen3:4b-instruct", "embeddings": "bge-m3", "juez": "qwen3:8b",
        "preguntas": 2, "recuperacion_acierto_k": 1.0, "recuperacion_recall_articulos": 1.0, "precision_citas": 1.0,
        "responde_cuando_debe": 1.0, "se_abstiene_cuando_debe": 1.0, "latencia_p50_s": 3.2, "latencia_p95_s": 3.2,
        "faithfulness": 0.5, "answer_relevancy": 1.0, "contextual_precision": 1.0, "contextual_recall": 1.0,
        "correctness": 0.9,
        "por_tipo": {"directa": {"n": 1, "comportamiento_correcto": 1.0}, "sin_respuesta": {"n": 1, "comportamiento_correcto": 1.0}},
    }
    carpeta = tmp_path / "eval" / "reportes"
    carpeta.mkdir(parents=True)
    contenido = json.dumps({"resumen": resumen, "resultados": resultados})
    (carpeta / "ultimo.json").write_text(contenido)
    (carpeta / "eval_20261023-142216.json").write_text(contenido)
    return resultados
