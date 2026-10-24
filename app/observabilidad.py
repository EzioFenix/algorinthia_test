"""Langfuse opcional: si no hay llaves, todo funciona igual y las observaciones son no-ops."""

import logging
import re
from contextlib import contextmanager
from functools import lru_cache

from app.config import config

log = logging.getLogger(__name__)

# Datos personales que no deben salir hacia Langfuse (preguntas de empleados).
_PATRONES_PII = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[correo]"),
    (re.compile(r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z\d]\d\b", re.IGNORECASE), "[curp]"),
    (re.compile(r"\b[A-ZÑ&]{3,4}\d{6}[A-Z\d]{3}\b", re.IGNORECASE), "[rfc]"),
    (re.compile(r"\b(?:\+?52\s?)?(?:\d[\s-]?){10}\b"), "[telefono]"),
]


def enmascarar(*, data, **_):
    if isinstance(data, str):
        for patron, reemplazo in _PATRONES_PII:
            data = patron.sub(reemplazo, data)
        return data
    if isinstance(data, dict):
        return {k: enmascarar(data=v) for k, v in data.items()}
    if isinstance(data, list):
        return [enmascarar(data=v) for v in data]
    return data


@lru_cache
def cliente():
    c = config()
    if not (c.langfuse_activo and c.langfuse_public_key and c.langfuse_secret_key):
        log.info("Langfuse desactivado (LANGFUSE_ACTIVO=0 o faltan LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY)")
        return None
    from langfuse import Langfuse

    return Langfuse(
        public_key=c.langfuse_public_key,
        secret_key=c.langfuse_secret_key,
        host=c.langfuse_host,
        mask=enmascarar,
    )


class _Nula:
    trace_id = None

    def update(self, **_):
        pass

    def score_trace(self, **_):
        pass


@contextmanager
def observacion(nombre: str, tipo: str = "span", **kwargs):
    lf = cliente()
    if lf is None:
        yield _Nula()
        return
    with lf.start_as_current_observation(name=nombre, as_type=tipo, **kwargs) as obs:
        yield obs


def url_traza(trace_id: str | None) -> str | None:
    """Enlace a la traza en el Langfuse local. Se arma sin consultar la red (el SDK haría una llamada y, con
    Langfuse caído, rompería /preguntar) y usa la dirección que ve el navegador, no la del contenedor."""
    c = config()
    if not (cliente() and trace_id):
        return None
    return f"{c.langfuse_public_url.rstrip('/')}/project/{c.langfuse_project_id}/traces/{trace_id}"


def vaciar() -> None:
    if lf := cliente():
        lf.flush()
