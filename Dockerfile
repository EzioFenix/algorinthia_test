# Imagen del asistente. Ollama corre fuera (en el host o en el servicio "ollama" de docker-compose).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DB_PATH=/app/estado/asistente.db \
    DIR_SUBIDAS=/app/estado/subidas

WORKDIR /app

# Dependencias primero (capa cacheable); el grupo "eval" permite correr la evaluación en el mismo contenedor.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --group eval --no-install-project

COPY app ./app
COPY eval ./eval
COPY data/fuentes ./data/fuentes

# Usuario sin privilegios
# /app/.deepeval: DeepEval guarda ahí su caché y el estado de la corrida (necesita escribir en el directorio de trabajo)
RUN useradd --create-home --uid 10001 asistente && mkdir -p /app/estado /app/.deepeval && chown -R asistente /app/estado /app/eval /app/.deepeval
USER asistente

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/salud', timeout=3)"

CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
