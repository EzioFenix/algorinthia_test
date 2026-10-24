"""Configuración leída de variables de entorno (o del archivo .env)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parent.parent


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=RAIZ / ".env", extra="ignore")

    # Modelo local
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen3:4b-instruct"
    embed_model: str = "bge-m3"
    llm_num_ctx: int = 8192
    llm_temperature: float = 0.2
    llm_max_tokens: int = 700
    llm_timeout_s: float = 120.0
    llm_keep_alive: str = "5m"   # cuánto se queda el modelo cargado entre preguntas (modo max: 1h)
    modo_app: str = "normal"     # "max" lo fija ./run.sh 3

    # Juez (solo evaluación)
    judge_provider: str = "ollama"
    judge_model: str = "qwen3:8b"

    # Langfuse (si faltan las llaves, la observabilidad se desactiva sin romper nada)
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"
    # Langfuse corre en local (docker compose, perfil "langfuse"). Desde el navegador se llega por localhost,
    # aunque el contenedor de la API lo vea como http://langfuse-web:3000.
    langfuse_public_url: str = "http://localhost:3000"
    langfuse_project_id: str = "asistente-laboral"
    langfuse_activo: bool = True

    # Costo de referencia en USD por 1M tokens (el modelo local cuesta $0 real)
    costo_entrada_usd_mtok: float = 0.10
    costo_salida_usd_mtok: float = 0.40

    # Búsqueda
    top_k: int = 6
    # Similitud coseno mínima: por debajo, la pregunta no tiene relación con los documentos
    umbral_sin_relacion: float = 0.42
    # Por debajo de esta similitud se intenta reescribir la pregunta en términos legales
    umbral_reescritura: float = 0.55

    # API
    api_key: str = ""
    max_pdf_mb: int = 50
    max_pdfs_por_trabajo: int = 10
    max_paginas_pdf: int = 2000
    max_pregunta_chars: int = 1000

    # Rutas
    db_path: Path = RAIZ / "data" / "asistente.db"
    dir_subidas: Path = RAIZ / "data" / "subidas"
    dir_fuentes: Path = RAIZ / "data" / "fuentes"
    dir_eval: Path = RAIZ / "eval"


@lru_cache
def config() -> Config:
    return Config()
