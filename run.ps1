# Punto de entrada único para Windows (PowerShell 5.1+): menú con Instalar y Correr.
#
#   .\run.ps1                 menú interactivo (elige 1 o 2)
#   .\run.ps1 1 -ConJuez      instalar: Docker Desktop + Ollama + modelos (el juez es solo para la evaluación)
#   .\run.ps1 2 [-SinLangfuse] correr:  levanta todo en Docker (con Langfuse local) y abre la interfaz
#   .\run.ps1 4               detener:  para contenedores y modelos (el modo MAX, el 3, solo existe en macOS)
#
# Si PowerShell bloquea el script:  powershell -ExecutionPolicy Bypass -File .\run.ps1
# Nota: este script no se ha probado en Windows real (se desarrolló en macOS).
param(
    [string]$Opcion = "",
    [switch]$ConJuez,
    [switch]$SinLangfuse   # Langfuse corre en local (6 contenedores, ~3 GB); esto lo omite
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Puerto = 8000

function Info($m)  { Write-Host "==> $m" -ForegroundColor Cyan }
function Ok($m)    { Write-Host "  OK $m" -ForegroundColor Green }
function Aviso($m) { Write-Host "  !  $m" -ForegroundColor Yellow }
function Falla($m) { Write-Host "  X  $m" -ForegroundColor Red; exit 1 }
function Tiene($c) { [bool](Get-Command $c -ErrorAction SilentlyContinue) }

# Lee una variable de .env sin ejecutarlo
function Leer-Env($clave, $defecto) {
    foreach ($archivo in ".env", ".env.example") {
        if (Test-Path $archivo) {
            $linea = Select-String -Path $archivo -Pattern "^$clave=(.*)$" | Select-Object -Last 1
            if ($linea) {
                $valor = $linea.Matches[0].Groups[1].Value.Trim().Trim('"', "'")
                if ($valor) { return $valor }
            }
        }
    }
    return $defecto
}

function Validar-Modelo($m) {
    if ($m -notmatch '^[A-Za-z0-9._:/-]+$') { Falla "Nombre de modelo inválido en .env: '$m'" }
}

function Actualizar-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

function Valor-Env($clave) {
    $l = Select-String -Path ".env" -Pattern "^$clave=(.*)$" | Select-Object -Last 1
    if ($l) { return $l.Matches[0].Groups[1].Value.Trim() } else { return "" }
}

function Poner-Env($clave, $valor) {
    $lineas = @(Get-Content ".env")
    if ($lineas -match "^$clave=") { $lineas = $lineas -replace "^$clave=.*$", "$clave=$valor" } else { $lineas += "$clave=$valor" }
    Set-Content ".env" $lineas
}

function Secreto($bytes) {
    $b = New-Object byte[] $bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    return (($b | ForEach-Object { $_.ToString("x2") }) -join "")
}

# Los secretos de Langfuse NO viven en el repositorio: se generan al azar la primera vez y quedan solo en .env.
function Asegurar-Secretos {
    $nuevos = $false
    $largos = [ordered]@{ LANGFUSE_NEXTAUTH_SECRET = 32; LANGFUSE_SALT = 32; LANGFUSE_ENCRYPTION_KEY = 32; LANGFUSE_POSTGRES_PASSWORD = 16
                          LANGFUSE_CLICKHOUSE_PASSWORD = 16; LANGFUSE_REDIS_AUTH = 16; LANGFUSE_MINIO_PASSWORD = 16; LANGFUSE_USER_PASSWORD = 12 }
    foreach ($c in $largos.Keys) { if (-not (Valor-Env $c)) { Poner-Env $c (Secreto $largos[$c]); $nuevos = $true } }
    if (-not (Valor-Env "LANGFUSE_PUBLIC_KEY")) { Poner-Env "LANGFUSE_PUBLIC_KEY" ("pk-lf-" + (Secreto 16)); $nuevos = $true }
    if (-not (Valor-Env "LANGFUSE_SECRET_KEY")) { Poner-Env "LANGFUSE_SECRET_KEY" ("sk-lf-" + (Secreto 16)); $nuevos = $true }
    if ((Valor-Env "LANGFUSE_HOST") -match "langfuse\.com") { Poner-Env "LANGFUSE_HOST" "http://localhost:3000"; Aviso "LANGFUSE_HOST apuntaba a la nube: ahora usa el Langfuse local." }
    if ($nuevos) { Ok "Se generaron los secretos de Langfuse en .env (usuario: admin@asistente.local, contraseña: LANGFUSE_USER_PASSWORD)." }
}

function Crear-Env {
    if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
        Copy-Item ".env.example" ".env"
        Ok "Se creó .env desde .env.example."
    }
    if (Test-Path ".env") { Asegurar-Secretos }
}

function Esperar-Langfuse {
    Info "Esperando a Langfuse (la primera vez descarga imágenes y migra la base: 2-4 min)"
    for ($i = 0; $i -lt 120; $i++) {
        try { Invoke-RestMethod "http://127.0.0.1:3000/api/public/health" -TimeoutSec 3 | Out-Null; Ok "Langfuse listo en http://127.0.0.1:3000"; return $true } catch { }
        Start-Sleep -Seconds 3
    }
    Aviso "Langfuse aún no responde; revisa:  docker compose --profile langfuse logs langfuse-web"
    return $false
}

$OllamaUrl = Leer-Env "OLLAMA_BASE_URL" "http://localhost:11434"
$Llm       = Leer-Env "LLM_MODEL" "qwen3:4b-instruct"
$Embed     = Leer-Env "EMBED_MODEL" "bge-m3"
$Juez      = Leer-Env "JUDGE_MODEL" "qwen3:8b"
$ApiKey    = Leer-Env "API_KEY" ""
foreach ($m in $Llm, $Embed, $Juez) { Validar-Modelo $m }

function Docker-Activo { docker info *> $null; return ($LASTEXITCODE -eq 0) }

function Asegurar-Docker {
    if (-not (Tiene "docker")) { Falla "Docker no está instalado: ejecuta primero la opción 1 (Instalar)." }
    if (-not (Docker-Activo)) {
        $exe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
        if (-not (Test-Path $exe)) { Falla "No se encontró Docker Desktop; ejecuta la opción 1." }
        Info "Iniciando Docker Desktop (puede tardar un minuto)"
        Start-Process $exe
        for ($i = 0; $i -lt 90; $i++) { if (Docker-Activo) { break }; Start-Sleep -Seconds 2 }
        if (-not (Docker-Activo)) { Falla "Docker Desktop no respondió. Ábrelo manualmente y vuelve a intentar." }
    }
    Ok "Docker listo"
}

function Ollama-Activo {
    try { Invoke-RestMethod "$OllamaUrl/api/version" -TimeoutSec 3 | Out-Null; return $true } catch { return $false }
}

function Iniciar-Ollama {
    if (Ollama-Activo) { Ok "Ollama responde en $OllamaUrl"; return }
    Info "Iniciando Ollama"
    $env:OLLAMA_NUM_PARALLEL = "1"; $env:OLLAMA_MAX_LOADED_MODELS = "2"; $env:OLLAMA_KEEP_ALIVE = "5m"
    Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
    for ($i = 0; $i -lt 30; $i++) { if (Ollama-Activo) { break }; Start-Sleep -Seconds 1 }
    if (-not (Ollama-Activo)) { Falla "Ollama no respondió en $OllamaUrl" }
    Ok "Ollama iniciado"
}

function Descargar-Modelo($m) {
    ollama show $m *> $null
    if ($LASTEXITCODE -eq 0) { Ok "$m ya está descargado" } else { Info "Descargando $m"; ollama pull $m; Ok "$m descargado" }
}

function Instalar {
    Info "Instalar · Windows"
    Crear-Env
    if (-not (Tiene "winget")) { Falla "Falta winget (App Installer de Microsoft Store). Instala Docker Desktop y Ollama a mano." }
    if (-not (Tiene "docker")) {
        Info "Instalando Docker Desktop (requiere WSL2 y puede pedir reiniciar)"
        winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
    } else { Ok "Docker ya está instalado" }
    if (-not (Tiene "ollama")) {
        Info "Instalando Ollama"
        winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
    } else { Ok "Ollama ya está instalado" }
    Actualizar-Path
    if (-not (Tiene "ollama")) { Falla "Ollama quedó instalado pero no está en el PATH: cierra y abre PowerShell y vuelve a ejecutar la opción 1." }

    Iniciar-Ollama
    Descargar-Modelo $Llm
    Descargar-Modelo $Embed
    $respuesta = if ($ConJuez) { "s" } else { Read-Host "  ¿Descargar también el juez $Juez (~5 GB, solo para la evaluación)? [s/N]" }
    if ($respuesta -match '^(s|si|y)$') { Descargar-Modelo $Juez } else { Aviso "Juez no descargado: antes de evaluar ejecuta  .\run.ps1 1 -ConJuez" }
    Info "Instalación terminada. Si Docker Desktop pidió reiniciar, hazlo. Siguiente paso:  .\run.ps1 2"
}

function Esperar-Documentos {
    $esperados = @(Get-ChildItem "data\fuentes\*.pdf" -ErrorAction SilentlyContinue).Count
    Info "Esperando a que se indexen los documentos (la primera vez tarda 1-2 min)"
    for ($i = 0; $i -lt 150; $i++) {
        try {
            $docs = Invoke-RestMethod "http://127.0.0.1:$Puerto/documentos" -Headers @{ "X-API-Key" = $ApiKey } -TimeoutSec 3
            if (@($docs).Count -ge $esperados) { return $true }
        } catch { }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Correr {
    Info "Correr · Windows"
    Crear-Env
    Asegurar-Docker
    if (-not (Tiene "ollama")) { Falla "Falta Ollama: ejecuta primero la opción 1 (Instalar)." }
    Iniciar-Ollama
    foreach ($m in $Llm, $Embed) {
        ollama show $m *> $null
        if ($LASTEXITCODE -ne 0) { Falla "Falta el modelo $m: ejecuta primero la opción 1 (Instalar)." }
    }
    if (-not $SinLangfuse) {
        Info "Levantando Langfuse local (observabilidad sin salir de tu máquina)"
        docker compose --profile langfuse up -d langfuse-web langfuse-worker
        Esperar-Langfuse | Out-Null
    } else {
        $env:LANGFUSE_ACTIVO = "0"
        Aviso "Sin Langfuse: las respuestas no dejarán traza."
    }
    Info "Construyendo y levantando la API"
    docker compose up -d --build api
    if ($LASTEXITCODE -ne 0) { Falla "No se pudo levantar la API. ¿El puerto $Puerto está ocupado?" }
    if (Esperar-Documentos) { Ok "Documentos indexados" } else { Aviso "Aún se está indexando; revisa:  docker compose logs -f api" }
    $url = "http://127.0.0.1:$Puerto"
    Write-Host "`n  Listo -> $url   (API: $url/docs)`n" -ForegroundColor Green
    if (-not $SinLangfuse) { Write-Host "    Trazas:        http://127.0.0.1:3000  (usuario admin@asistente.local; contraseña: LANGFUSE_USER_PASSWORD en .env)" }
    Write-Host "    Ver logs:      docker compose logs -f api"
    Write-Host "    Evaluación:    docker compose run --rm eval"
    Write-Host "    Detener todo:  docker compose --profile langfuse down`n"
    Start-Process $url
}

function Detener {
    Info "Detener todo"
    if ((Tiene "docker") -and (Docker-Activo)) {
        docker compose --profile ollama --profile langfuse --profile eval down --remove-orphans *> $null
        Ok "Contenedores detenidos (tus datos siguen en los volúmenes de Docker)"
    }
    if ((Tiene "ollama") -and (Ollama-Activo)) {
        $cargados = @(ollama ps | Select-Object -Skip 1 | ForEach-Object { ($_ -split "\s+")[0] } | Where-Object { $_ })
        foreach ($m in $cargados) { ollama stop $m *> $null; Ok "Modelo descargado de memoria: $m" }
    }
    Info "Todo detenido. Para volver:  .\run.ps1 2   (Docker Desktop se cierra desde su icono si quieres liberar su memoria)"
}

if (-not $IsWindows -and $PSVersionTable.PSEdition -eq "Core") { Falla "Este script es para Windows. En macOS/Linux usa ./run.sh" }

if (-not $Opcion) {
    Write-Host "`n  Asistente de derechos laborales · sistema detectado: Windows`n"
    Write-Host "    1) Instalar   Docker Desktop, Ollama y modelos"
    Write-Host "    2) Correr     levanta todo en Docker"
    Write-Host "    4) Detener    para contenedores y modelos"
    Write-Host "    0) Salir`n"
    $Opcion = Read-Host "  Elige una opción [1/2/4/0]"
}
switch ($Opcion) {
    { $_ -in "1", "instalar" } { Instalar }
    { $_ -in "2", "correr" }   { Correr }
    { $_ -in "4", "detener" }  { Detener }
    "3"                        { Falla "El modo MAX usa un modelo MLX: solo existe en macOS con Apple Silicon." }
    "0"                        { exit 0 }
    default                    { Falla "Opción no válida: '$Opcion' (elige 1, 2 o 0)" }
}
