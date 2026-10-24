"""Juez local para DeepEval: modelo de Ollama distinto al generador, con salida JSON forzada por esquema."""

import httpx
from deepeval.models import DeepEvalBaseLLM
from pydantic import BaseModel

from app.config import config


class JuezOllama(DeepEvalBaseLLM):
    def __init__(self, modelo: str | None = None) -> None:
        self.modelo = modelo or config().judge_model
        self.url = f"{config().ollama_base_url}/api/chat"
        super().__init__(self.modelo)

    def load_model(self, *args, **kwargs):
        return self

    def get_model_name(self, *args, **kwargs) -> str:
        return f"ollama/{self.modelo}"

    def _cuerpo(self, prompt: str, schema: type[BaseModel] | None) -> dict:
        cuerpo = {
            "model": self.modelo,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 1500},
        }
        if schema is not None:
            cuerpo["format"] = schema.model_json_schema()
        return cuerpo

    @staticmethod
    def _resultado(contenido: str, schema: type[BaseModel] | None):
        return schema.model_validate_json(contenido) if schema is not None else contenido

    def generate(self, prompt: str, schema: type[BaseModel] | None = None, **kwargs):
        r = httpx.post(self.url, json=self._cuerpo(prompt, schema), timeout=600)
        r.raise_for_status()
        return self._resultado(r.json()["message"]["content"], schema)

    async def a_generate(self, prompt: str, schema: type[BaseModel] | None = None, **kwargs):
        async with httpx.AsyncClient(timeout=600) as cliente:
            r = await cliente.post(self.url, json=self._cuerpo(prompt, schema))
        r.raise_for_status()
        return self._resultado(r.json()["message"]["content"], schema)
