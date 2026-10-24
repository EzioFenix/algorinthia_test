correr:        ## levanta todo en Docker (equivale a ./run.sh 2)
	./run.sh 2

.PHONY: correr instalar servir test eval eval-rapida comparar-juez seguridad docker

instalar:      ## Docker + Ollama + modelos (incluye el juez)
	./run.sh 1 --con-juez

servir:        ## API + interfaz en http://127.0.0.1:8000
	uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

test:
	uv run pytest -q

eval:          ## evaluación completa: métricas propias + DeepEval con juez local
	uv run python -m eval.correr_eval

eval-rapida:   ## solo métricas deterministas (sin juez)
	uv run python -m eval.correr_eval --sin-juez

seguridad:
	uv run bandit -r app -q
	uv run ruff check --select S app
	uv run pip-audit

docker:
	docker compose up --build

comparar-juez: ## compara la calificación manual con la del juez
	uv run python -m eval.comparar_manual
