#!/usr/bin/env bash
# Punto de entrada único: detecta el sistema y ofrece Instalar, Correr, MAX o Detener.
#
#   ./run.sh                     menú interactivo (elige un número)
#   ./run.sh 1 [--con-juez]      instalar:  Docker + Ollama + modelos (el juez es solo para la evaluación)
#   ./run.sh 2 [--sin-langfuse]  correr:    todo en Docker, con Langfuse local, y abre la interfaz
#   ./run.sh 3 [--evaluar] [--sin-langfuse]  max: detiene lo demás y usa qwen3.8:27b-mlx (con trazas); --evaluar lo evalúa (solo Mac Apple Silicon)
#   ./run.sh 4                   detener:   para contenedores, modelos y Colima
#
# macOS y Linux (incluye WSL2). En Windows nativo usa run.ps1.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RAIZ"

PUERTO=8000
CON_JUEZ=0
EVALUAR_MAX=0       # en modo max: además corre la evaluación completa con el modelo grande
USAR_LANGFUSE=1   # Langfuse corre en local (6 contenedores, ~3 GB), también en modo max. --sin-langfuse lo omite

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
aviso() { printf '\033[1;33m  !\033[0m %s\n' "$*" >&2; }
error() { printf '\033[1;31m  ✗\033[0m %s\n' "$*" >&2; exit 1; }
tiene() { command -v "$1" >/dev/null 2>&1; }

confirmar() {  # confirmar "mensaje": responde no si no hay terminal interactiva
  [ -t 0 ] || return 1
  local r
  read -r -p "  $1 [s/N] " r || return 1
  case "$r" in s|S|si|SI|Si|y|Y) return 0 ;; *) return 1 ;; esac
}

# --- Sistema ----------------------------------------------------------------
detectar_so() {
  case "$(uname -s)" in
    Darwin) SO=macos; NOMBRE_SO="macOS $(uname -m)" ;;
    Linux)
      if grep -qi microsoft /proc/version 2>/dev/null; then SO=wsl; NOMBRE_SO="Linux (WSL2)"; else SO=linux; NOMBRE_SO="Linux $(uname -m)"; fi ;;
    MINGW*|MSYS*|CYGWIN*) SO=windows; NOMBRE_SO="Windows" ;;
    *) SO=desconocido; NOMBRE_SO="$(uname -s)" ;;
  esac
  case "$SO" in
    windows) error "En Windows nativo usa PowerShell:  .\\run.ps1   (o ejecuta este script dentro de WSL2)." ;;
    desconocido) error "Sistema no soportado: $NOMBRE_SO" ;;
  esac
}

# Lee una variable de .env sin ejecutarlo: hacer `source` correría cualquier código del archivo.
leer_env() {
  local clave="$1" defecto="$2" archivo valor
  for archivo in .env .env.example; do
    [ -f "$archivo" ] || continue
    valor="$(sed -n "s/^${clave}=//p" "$archivo" | tail -n1 | tr -d "\"'\r")"
    if [ -n "$valor" ]; then printf '%s' "$valor"; return; fi
  done
  printf '%s' "$defecto"
}

validar_modelo() {
  printf '%s' "$1" | grep -Eq '^[A-Za-z0-9._:/-]+$' || error "Nombre de modelo inválido en .env: '$1'"
}

cargar_config() {
  OLLAMA_URL="$(leer_env OLLAMA_BASE_URL http://localhost:11434)"
  LLM_MODEL="$(leer_env LLM_MODEL qwen3:4b-instruct)"
  EMBED_MODEL="$(leer_env EMBED_MODEL bge-m3)"
  JUDGE_MODEL="$(leer_env JUDGE_MODEL qwen3:8b)"
  MODELO_MAX="$(leer_env MODELO_MAX qwen3.8:27b-mlx)"
  API_KEY="$(leer_env API_KEY '')"
  for m in "$LLM_MODEL" "$EMBED_MODEL" "$JUDGE_MODEL" "$MODELO_MAX"; do validar_modelo "$m"; done
}

valor_env() { sed -n "s/^$1=//p" .env | tail -n1 | tr -d '\r'; }

poner_env() {  # poner_env CLAVE VALOR → agrega o reemplaza en .env (los valores son hexadecimales: seguros para sed)
  if grep -q "^$1=" .env; then sed -i.bak "s|^$1=.*|$1=$2|" .env && rm -f .env.bak; else printf '%s=%s\n' "$1" "$2" >> .env; fi
}

# Los secretos de Langfuse NO viven en el repositorio: se generan al azar la primera vez y quedan solo en .env.
asegurar_secretos() {
  tiene openssl || error "Falta openssl para generar los secretos de Langfuse."
  local par clave largo nuevos=0
  for par in LANGFUSE_NEXTAUTH_SECRET:32 LANGFUSE_SALT:32 LANGFUSE_ENCRYPTION_KEY:32 LANGFUSE_POSTGRES_PASSWORD:16 \
             LANGFUSE_CLICKHOUSE_PASSWORD:16 LANGFUSE_REDIS_AUTH:16 LANGFUSE_MINIO_PASSWORD:16 LANGFUSE_USER_PASSWORD:12; do
    clave="${par%%:*}"; largo="${par##*:}"
    [ -n "$(valor_env "$clave")" ] || { poner_env "$clave" "$(openssl rand -hex "$largo")"; nuevos=1; }
  done
  [ -n "$(valor_env LANGFUSE_PUBLIC_KEY)" ] || { poner_env LANGFUSE_PUBLIC_KEY "pk-lf-$(openssl rand -hex 16)"; nuevos=1; }
  [ -n "$(valor_env LANGFUSE_SECRET_KEY)" ] || { poner_env LANGFUSE_SECRET_KEY "sk-lf-$(openssl rand -hex 16)"; nuevos=1; }
  case "$(valor_env LANGFUSE_HOST)" in  # .env de una versión anterior que apuntaba a la nube
    *langfuse.com*) poner_env LANGFUSE_HOST "http://localhost:3000"; aviso "LANGFUSE_HOST apuntaba a la nube: ahora usa el Langfuse local." ;;
  esac
  [ "$nuevos" -eq 0 ] || ok "Se generaron los secretos de Langfuse en .env (usuario: admin@asistente.local, contraseña: LANGFUSE_USER_PASSWORD)."
}

crear_env() {
  if [ ! -f .env ] && [ -f .env.example ]; then
    cp .env.example .env
    chmod 600 .env
    ok "Se creó .env desde .env.example."
  fi
  [ -f .env ] && asegurar_secretos
  return 0
}

compose() {
  if docker compose version >/dev/null 2>&1; then docker compose "$@"; else docker-compose "$@"; fi
}

# --- Docker -----------------------------------------------------------------
configurar_plugins_docker() {  # Homebrew instala compose/buildx como plugins que Docker debe localizar
  local cfg="$HOME/.docker/config.json" dir
  dir="$(brew --prefix)/lib/docker/cli-plugins"
  if [ ! -f "$cfg" ]; then
    mkdir -p "$HOME/.docker"
    printf '{\n  "cliPluginsExtraDirs": ["%s"]\n}\n' "$dir" > "$cfg"
    ok "Creado $cfg para que Docker encuentre compose y buildx"
  elif ! grep -q cliPluginsExtraDirs "$cfg"; then
    aviso "Agrega esta línea a $cfg para que 'docker compose' funcione:  \"cliPluginsExtraDirs\": [\"$dir\"]"
  fi
}

instalar_docker() {
  if tiene docker && { docker compose version >/dev/null 2>&1 || tiene docker-compose; }; then
    ok "Docker y Compose ya están instalados"
    return
  fi
  case "$SO" in
    macos)
      tiene brew || error "Falta Homebrew (https://brew.sh); instálalo y vuelve a ejecutar."
      info "Instalando Colima + Docker CLI (ligero, sin Docker Desktop)"
      brew install colima docker docker-compose docker-buildx
      configurar_plugins_docker
      ;;
    linux|wsl)
      aviso "Se instalará Docker Engine con el script oficial de https://get.docker.com (requiere sudo)."
      confirmar "¿Continuar?" || error "Instala Docker a mano (https://docs.docker.com/engine/install/) y vuelve a ejecutar."
      curl -fsSL https://get.docker.com | sudo sh
      sudo usermod -aG docker "$USER" || true
      aviso "Cierra sesión y vuelve a entrar (o ejecuta 'newgrp docker') para usar Docker sin sudo."
      ;;
  esac
  ok "Docker instalado"
}

asegurar_docker() {
  tiene docker || error "Docker no está instalado: ejecuta primero la opción 1 (Instalar)."
  if ! docker info >/dev/null 2>&1; then
    case "$SO" in
      macos)
        tiene colima || error "Falta Colima: ejecuta primero la opción 1 (Instalar)."
        if [ "$USAR_LANGFUSE" -eq 1 ]; then
          info "Iniciando Colima (4 CPU, 6 GB: la API más Langfuse local)"
          colima start --cpu 4 --memory 6 --disk 40
        else
          info "Iniciando Colima (2 CPU, 4 GB: suficiente para la API)"
          colima start --cpu 2 --memory 4 --disk 40
        fi
        ;;
      linux|wsl)
        info "Iniciando el servicio de Docker"
        sudo systemctl start docker 2>/dev/null || sudo service docker start 2>/dev/null || true
        ;;
    esac
    docker info >/dev/null 2>&1 || error "Docker no responde. En Linux, ¿tu usuario está en el grupo 'docker'?"
  fi
  ok "Docker listo"
}

asegurar_memoria() {  # Langfuse (ClickHouse, Postgres, Redis, MinIO…) necesita más que la API sola
  [ "$SO" = macos ] || return 0
  local bytes
  bytes="$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)"
  if [ "${bytes:-0}" -lt $((5500 * 1024 * 1024)) ]; then
    aviso "Colima tiene $((bytes / 1024 / 1024)) MB; Langfuse local necesita ~6 GB. Reiniciando Colima con 4 CPU y 6 GB (tus volúmenes se conservan)."
    colima stop && colima start --cpu 4 --memory 6 --disk 40
  fi
}

esperar_langfuse() {
  info "Esperando a Langfuse (la primera vez descarga imágenes y migra la base: 2–4 min)"
  for _ in $(seq 1 120); do
    curl -fs --max-time 3 "http://127.0.0.1:3000/api/public/health" >/dev/null 2>&1 && { ok "Langfuse listo en http://127.0.0.1:3000"; return 0; }
    sleep 3
  done
  aviso "Langfuse aún no responde; revisa:  docker compose --profile langfuse logs langfuse-web"
  return 1
}

# --- Ollama en el host (solo macOS: así usa la GPU Metal) -------------------------
ollama_activo() { curl -fsS --max-time 3 "$OLLAMA_URL/api/version" >/dev/null 2>&1; }

iniciar_ollama() {
  if ollama_activo; then ok "Ollama responde en $OLLAMA_URL"; return; fi
  case "$OLLAMA_URL" in
    *localhost*|*127.0.0.1*) ;;
    *) error "Ollama no responde en $OLLAMA_URL (servidor remoto: no se puede iniciar desde aquí)." ;;
  esac
  local log="${TMPDIR:-/tmp}/ollama-serve.log"
  info "Iniciando Ollama en modo de bajo consumo (log: $log)"
  # Solo escucha en 127.0.0.1: la API de Ollama no tiene autenticación.
  OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=2 OLLAMA_KEEP_ALIVE=5m \
  OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 nohup ollama serve >"$log" 2>&1 &
  mkdir -p "$RAIZ/.run" && echo $! > "$RAIZ/.run/ollama.pid"   # para que "detener" solo cierre el que inició run.sh
  for _ in $(seq 1 30); do ollama_activo && break; sleep 1; done
  ollama_activo || error "Ollama no respondió; revisa $log"
  ok "Ollama iniciado"
}

descargar_modelo() {
  if ollama show "$1" >/dev/null 2>&1; then ok "$1 ya está descargado"; else info "Descargando $1"; ollama pull "$1"; ok "$1 descargado"; fi
}

# --- 1) Instalar --------------------------------------------------------------
instalar() {
  info "Instalar · $NOMBRE_SO"
  crear_env
  instalar_docker

  if [ "$SO" = macos ]; then
    tiene ollama || { info "Instalando Ollama"; brew install ollama; }
    iniciar_ollama
    descargar_modelo "$LLM_MODEL"
    descargar_modelo "$EMBED_MODEL"
    if ollama show "$JUDGE_MODEL" >/dev/null 2>&1; then
      ok "Juez $JUDGE_MODEL ya está descargado"
    elif [ "$CON_JUEZ" -eq 1 ] || confirmar "¿Descargar también el modelo juez $JUDGE_MODEL (~5 GB, solo para la evaluación)?"; then
      descargar_modelo "$JUDGE_MODEL"
    else
      aviso "Juez no descargado: antes de evaluar ejecuta  ./run.sh 1 --con-juez"
    fi
  else
    ok "En Linux, Ollama y los modelos corren en un contenedor: se descargan al elegir la opción 2."
    aviso "Para evaluar con el juez en Linux:  PULL_JUDGE=1 ./run.sh 2"
  fi

  if [ -f pyproject.toml ] && confirmar "¿Instalar también el entorno local de Python (uv) para 'make test' y 'make eval' fuera de Docker?"; then
    tiene uv || { if [ "$SO" = macos ]; then brew install uv; else curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; fi; }
    uv python install 3.12
    uv sync
    ok "Entorno local listo (.venv)"
  fi

  info "Instalación terminada. Siguiente paso:  ./run.sh 2"
}

# --- 2) Correr ----------------------------------------------------------------
esperar_documentos() {
  local esperados docs
  esperados="$(ls data/fuentes/*.pdf 2>/dev/null | wc -l | tr -d ' ')"
  info "Esperando a que se indexen los documentos (la primera vez tarda 1–2 min)"
  for _ in $(seq 1 150); do
    docs="$(curl -fs --max-time 3 -H "X-API-Key: ${API_KEY}" "http://127.0.0.1:$PUERTO/documentos" 2>/dev/null | grep -o '"clave"' | wc -l | tr -d ' ' || true)"
    [ "${docs:-0}" -ge "${esperados:-1}" ] && return 0
    sleep 2
  done
  return 1
}

correr() {
  info "Correr · $NOMBRE_SO"
  crear_env
  asegurar_docker
  [ "$USAR_LANGFUSE" -eq 0 ] || asegurar_memoria

  if [ "$SO" = macos ]; then
    tiene ollama || error "Falta Ollama: ejecuta primero la opción 1 (Instalar)."
    iniciar_ollama
    for m in $(modelos_cargados); do  # (sin "grep -q" en una tubería: con pipefail la deja en falso)
      [ "$m" = "$MODELO_MAX" ] && ollama stop "$MODELO_MAX" >/dev/null 2>&1 && ok "Se liberó el modelo max de memoria"
    done
    for m in "$LLM_MODEL" "$EMBED_MODEL"; do
      ollama show "$m" >/dev/null 2>&1 || error "Falta el modelo $m: ejecuta primero la opción 1 (Instalar)."
    done
  else
    export OLLAMA_BASE_URL_DOCKER=http://ollama:11434
    info "Iniciando Ollama en un contenedor y descargando los modelos (solo la primera vez)"
    compose --profile ollama up -d ollama
    compose --profile ollama run --rm ollama-modelos
  fi

  if [ "$USAR_LANGFUSE" -eq 1 ]; then
    info "Levantando Langfuse local (observabilidad sin salir de tu máquina)"
    compose --profile langfuse up -d langfuse-web langfuse-worker
    esperar_langfuse || true
  else
    export LANGFUSE_ACTIVO=0
    aviso "Sin Langfuse: las respuestas no dejarán traza."
  fi

  info "Construyendo y levantando la API"
  compose up -d --build api || error "No se pudo levantar la API. ¿El puerto $PUERTO está ocupado?"

  if esperar_documentos; then
    ok "Documentos indexados"
  else
    aviso "Aún se está indexando; revisa el avance con:  docker compose logs -f api"
  fi

  local url="http://127.0.0.1:$PUERTO"
  printf '\n  \033[1;32mListo →\033[0m %s   (API: %s/docs)\n\n' "$url" "$url"
  if [ "$USAR_LANGFUSE" -eq 1 ]; then
    printf '    Trazas:        http://127.0.0.1:3000  (usuario admin@asistente.local; contraseña: LANGFUSE_USER_PASSWORD en .env)\n'
  fi
  printf '    Ver logs:      docker compose logs -f api\n'
  printf '    Evaluación:    docker compose run --rm eval\n'
  printf '    Detener todo:  docker compose --profile ollama --profile langfuse down\n\n'
  case "$SO" in
    macos) open "$url" >/dev/null 2>&1 || true ;;
    linux) { tiene xdg-open && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && xdg-open "$url" >/dev/null 2>&1; } || true ;;
  esac
}

# --- 3) MAX ---------------------------------------------------------------------
modelos_cargados() { ollama ps 2>/dev/null | awk 'NR > 1 {print $1}'; }

hay_evaluacion() {  # una evaluación corriendo en un contenedor o directamente en el Mac (make eval)
  [ -n "$(docker ps -q --filter label=com.docker.compose.service=eval 2>/dev/null)" ] || pgrep -f "eval.correr_eval" >/dev/null 2>&1
}

# Una evaluación completa tarda ~1 h: no se interrumpe sin preguntar (sin terminal interactiva, la respuesta es "no").
proteger_evaluacion() {
  if hay_evaluacion; then
    aviso "Hay una evaluación en curso ($1 la interrumpiría o la frenaría y se perdería su avance)."
    confirmar "¿Continuar de todos modos?" || error "Cancelado. Espera a que termine la evaluación y vuelve a intentarlo."
  fi
}

matar_los_demas() {
  info "Liberando recursos: se detiene todo lo que no sea el modelo max"
  if [ "$USAR_LANGFUSE" -eq 0 ]; then  # solo con --sin-langfuse: por defecto el modo max conserva las trazas
    compose --profile langfuse stop >/dev/null 2>&1 && ok "Langfuse detenido (sus datos se conservan)"
  fi
  compose --profile ollama stop >/dev/null 2>&1 || true
  local ev; ev="$(docker ps -q --filter label=com.docker.compose.service=eval 2>/dev/null || true)"
  [ -z "$ev" ] || { docker rm -f $ev >/dev/null 2>&1 && ok "Evaluación en curso detenida"; }
  pkill -f "uvicorn app.main:app" 2>/dev/null && ok "Servidores locales de la API detenidos" || true
  local m
  for m in $(modelos_cargados); do
    case "$m" in "$MODELO_MAX"*|"$EMBED_MODEL"*) ;; *) ollama stop "$m" >/dev/null 2>&1 && ok "Modelo descargado de memoria: $m" ;; esac
  done
}

maximo() {
  info "Modo MAX · $MODELO_MAX"
  proteger_evaluacion "el modo max"
  { [ "$SO" = macos ] && [ "$(uname -m)" = arm64 ]; } || error "El modo max usa un modelo MLX: solo funciona en macOS con Apple Silicon."
  tiene ollama || error "Falta Ollama: ejecuta primero la opción 1 (Instalar)."
  crear_env
  iniciar_ollama
  ollama show "$EMBED_MODEL" >/dev/null 2>&1 || error "Falta el modelo de embeddings $EMBED_MODEL (siempre hace falta para buscar): ejecuta la opción 1."
  if ! ollama show "$MODELO_MAX" >/dev/null 2>&1; then
    aviso "Falta el modelo $MODELO_MAX (~18 GB)."
    confirmar "¿Descargarlo ahora?" && ollama pull "$MODELO_MAX" || error "Sin $MODELO_MAX no hay modo max:  ollama pull $MODELO_MAX"
  fi
  asegurar_docker
  [ "$USAR_LANGFUSE" -eq 0 ] || asegurar_memoria
  matar_los_demas

  # El 27B es lento y pesado: más tiempo por respuesta y se mantiene cargado una hora entre preguntas.
  export MODO_APP=max MODO_LLM_MODEL="$MODELO_MAX" MODO_KEEP_ALIVE=1h MODO_TIMEOUT_S=300
  if [ "$USAR_LANGFUSE" -eq 1 ]; then
    info "Langfuse local sigue activo en modo max (las trazas muestran la respuesta del modelo grande)"
    compose --profile langfuse up -d langfuse-web langfuse-worker
    esperar_langfuse || true
  else
    export LANGFUSE_ACTIVO=0
  fi

  info "Cargando $MODELO_MAX en memoria (primera vez ~30–90 s)"
  curl -fsS --max-time 300 "$OLLAMA_URL/api/generate" -d "{\"model\":\"$MODELO_MAX\",\"prompt\":\"\",\"keep_alive\":\"1h\",\"stream\":false}" >/dev/null \
    && ok "Modelo cargado" || aviso "No se pudo precargar; se cargará con la primera pregunta."

  info "Levantando la API con el modelo max"
  compose up -d --build api || error "No se pudo levantar la API. ¿El puerto $PUERTO está ocupado?"
  esperar_documentos && ok "Documentos indexados" || aviso "Aún se está indexando; revisa:  docker compose logs -f api"
  local url="http://127.0.0.1:$PUERTO"
  printf '\n  \033[1;32mMAX listo →\033[0m %s   (modelo %s)\n\n' "$url" "$MODELO_MAX"
  printf '    Vuelve al modo normal:  ./run.sh 2     ·     Para todo:  ./run.sh 4\n\n'
  open "$url" >/dev/null 2>&1 || true

  if [ "$EVALUAR_MAX" -eq 0 ] && confirmar "¿Evaluar también con el modelo max? (≈ 1 h; se guarda como corrida «max» y no pisa la principal)"; then EVALUAR_MAX=1; fi
  if [ "$EVALUAR_MAX" -eq 1 ]; then
    ollama show "$JUDGE_MODEL" >/dev/null 2>&1 || error "Falta el juez $JUDGE_MODEL: ejecuta  ./run.sh 1 --con-juez"
    info "Evaluando $MODELO_MAX con el juez $JUDGE_MODEL (≈ 1 h). Reporte: eval/reportes/*_max.json, visible en Evaluación"
    compose run --rm eval /app/.venv/bin/python -m eval.correr_eval --etiqueta max
  fi
}

# --- 4) Detener -----------------------------------------------------------------
detener() {
  info "Detener todo"
  proteger_evaluacion "detener todo"
  if tiene docker && docker info >/dev/null 2>&1; then
    compose --profile ollama --profile langfuse --profile eval down --remove-orphans >/dev/null 2>&1 \
      && ok "Contenedores detenidos (tus datos siguen en los volúmenes de Docker)"
  fi
  pkill -f "uvicorn app.main:app" 2>/dev/null && ok "Servidores locales de la API detenidos" || true
  if tiene ollama && ollama_activo; then
    local m
    for m in $(modelos_cargados); do ollama stop "$m" >/dev/null 2>&1 && ok "Modelo descargado de memoria: $m"; done
  fi
  if [ -f "$RAIZ/.run/ollama.pid" ]; then
    kill "$(cat "$RAIZ/.run/ollama.pid")" 2>/dev/null && ok "Ollama detenido (lo había iniciado run.sh)"
    rm -f "$RAIZ/.run/ollama.pid"
  elif tiene ollama && ollama_activo; then
    aviso "Ollama sigue activo porque no lo inició run.sh; ciérralo desde su aplicación si quieres."
  fi
  if [ "$SO" = macos ] && tiene colima && colima status >/dev/null 2>&1; then
    colima stop >/dev/null 2>&1 && ok "Colima detenido (libera la memoria de la máquina virtual)"
  fi
  info "Todo detenido. Para volver:  ./run.sh 2"
}

# --- Menú -----------------------------------------------------------------------
menu() {
  printf '\n  \033[1mAsistente de derechos laborales\033[0m · sistema detectado: %s\n\n' "$NOMBRE_SO"
  printf '    1) Instalar   Docker, Ollama y modelos\n'
  printf '    2) Correr     levanta todo en Docker\n'
  printf '    3) MAX        detiene lo demás y usa %s\n' "$MODELO_MAX"
  printf '    4) Detener    para contenedores, modelos y Colima\n'
  printf '    0) Salir\n\n'
  local op
  read -r -p "  Elige una opción [1/2/3/4/0]: " op
  OPCION="$op"
}

main() {
  OPCION=""
  for arg in "$@"; do
    case "$arg" in
      --con-juez) CON_JUEZ=1 ;;
      --sin-langfuse) USAR_LANGFUSE=0 ;;
      --con-langfuse) ;;  # compatibilidad: en modo max Langfuse ya queda activo por defecto
      --evaluar) EVALUAR_MAX=1 ;;
      1|instalar) OPCION=1 ;;
      2|correr) OPCION=2 ;;
      3|max) OPCION=3 ;;
      4|detener) OPCION=4 ;;
      -h|--help|--ayuda) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
      *) error "Opción desconocida: $arg  (usa 1, 2, 3, 4 o --ayuda)" ;;
    esac
  done
  detectar_so
  cargar_config
  [ -n "$OPCION" ] || menu
  case "$OPCION" in
    1) instalar ;;
    2) correr ;;
    3) maximo ;;
    4) detener ;;
    0) exit 0 ;;
    *) error "Opción no válida: '$OPCION' (elige 1, 2, 3, 4 o 0)" ;;
  esac
}

main "$@"
