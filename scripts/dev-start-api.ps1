# dev-start-api.ps1
# Inicia a API FastAPI localmente com hot-reload
# Uso: .\scripts\dev-start-api.ps1

Write-Host "=== Iniciando API FastAPI (Market Alert) ===" -ForegroundColor Cyan
Write-Host ""

# Verificar se venv está ativado
if (-not (Test-Path env:VIRTUAL_ENV)) {
    Write-Host "Ativando virtual environment..." -ForegroundColor Yellow
    & .\.venv\Scripts\Activate.ps1
}

# Determinar raiz do repositório e configurar PYTHONPATH
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoRoot = (Resolve-Path (Join-Path $scriptDir '..')).Path
$backendRoot = Join-Path $repoRoot 'backend'

# Garantir que o Python encontre os pacotes shared e market_alert
if (-not $env:PYTHONPATH) { $env:PYTHONPATH = $backendRoot } else { $env:PYTHONPATH = "$backendRoot;$env:PYTHONPATH" }

# Garantir que o ConfigBase carregue o arquivo de ambiente específico do serviço
# (o código procura por ENV_FILE quando SERVICE_NAME não está definido)
$env:ENV_FILE = (Resolve-Path (Join-Path $repoRoot 'backend/market_alert/.env.market_alert')).Path

# Carregar .env.common primeiro (contendo variáveis críticas como SECRET_KEY, DATABASE_URL)
# Em seguida, carregar .env.market_alert para sobrescrever valores compartilhados quando apropriado.
function Load-EnvFile($path, $options) {
    if (-not (Test-Path $path)) { return }
    $lines = Get-Content $path -ErrorAction SilentlyContinue
    foreach ($raw in $lines) {
        $line = $raw.Trim()
        if ($line -eq '' -or $line.StartsWith('#')) { continue }
        $idx = $line.IndexOf('=')
        if ($idx -lt 0) { continue }
        $key = $line.Substring(0, $idx).Trim()
        $value = $line.Substring($idx + 1)
        $value = $value.Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        switch ($options) {
            'set-if-missing' {
                $cur = [System.Environment]::GetEnvironmentVariable($key, 'Process')
                if (-not $cur) { [System.Environment]::SetEnvironmentVariable($key, $value, 'Process') }
            }
            'overwrite-common' {
                # sobrescreve apenas valores carregados anteriormente do arquivo comum
                $cur = [System.Environment]::GetEnvironmentVariable($key, 'Process')
                if (-not $cur -or $script:loadedFromCommon.ContainsKey($key)) {
                    [System.Environment]::SetEnvironmentVariable($key, $value, 'Process')
                }
            }
            default {
                $cur = [System.Environment]::GetEnvironmentVariable($key, 'Process')
                if (-not $cur) { [System.Environment]::SetEnvironmentVariable($key, $value, 'Process') }
            }
        }
    }
}

# Hashtable para rastrear chaves carregadas do .env.common
$script:loadedFromCommon = @{}
$commonPath = (Resolve-Path (Join-Path $repoRoot '.env.common'))
if (Test-Path $commonPath) {
    Get-Content $commonPath | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq '' -or $line.StartsWith('#')) { return }
        $idx = $line.IndexOf('=')
        if ($idx -lt 0) { return }
        $key = $line.Substring(0, $idx).Trim()
        $script:loadedFromCommon[$key] = $true
    }
    Load-EnvFile $commonPath 'set-if-missing'
    Write-Host "Carregado: $commonPath" -ForegroundColor Green
} else {
    Write-Host ".env.common não encontrado em $repoRoot" -ForegroundColor Yellow
}

# Carregar o arquivo específico do serviço e permitir sobrescrever valores comuns
$serviceEnvPath = (Resolve-Path (Join-Path $repoRoot 'backend/market_alert/.env.market_alert'))
if (Test-Path $serviceEnvPath) {
    Load-EnvFile $serviceEnvPath 'overwrite-common'
    Write-Host "Carregado: $serviceEnvPath" -ForegroundColor Green
}

# Ajustes automáticos para desenvolvimento local quando infra roda em Docker
# Se os hostnames do compose (db, redis) NÃO forem resolvíveis a partir do host
# mas as portas padrão estiverem abertas em localhost, sobrescreve apenas as
# variáveis de ambiente do processo para apontar para localhost (não altera
# arquivos .env nem a configuração do docker-compose).
function CanResolveHost($h) {
    try { [System.Net.Dns]::GetHostEntry($h) | Out-Null; return $true } catch { return $false }
}

function PortOpen($host, $port) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $async = $tcp.BeginConnect($host, $port, $null, $null)
        $wait = $async.AsyncWaitHandle.WaitOne(500)
        if (-not $wait) { return $false }
        $tcp.EndConnect($async)
        $tcp.Close()
        return $true
    } catch { return $false }
}

# Ajuste DATABASE_URL para usar localhost se 'db' não resolver mas postgres estiver
if (-not (CanResolveHost 'db')) {
    if (PortOpen 'localhost' 5432) {
        if ($env:DATABASE_URL) {
            $env:DATABASE_URL = $env:DATABASE_URL -replace '@db:', '@localhost:'
            $env:DATABASE_URL = $env:DATABASE_URL -replace '://db:', '://localhost:'
        } else {
            if ($env:POSTGRES_USER -and $env:POSTGRES_PASSWORD -and $env:POSTGRES_DB) {
                $env:DATABASE_URL = "postgresql+psycopg2://$env:POSTGRES_USER:$env:POSTGRES_PASSWORD@localhost:5432/$env:POSTGRES_DB"
            }
        }
        Write-Host "Ajustado DATABASE_URL para localhost (dev)." -ForegroundColor Yellow
    }
}

# Ajuste REDIS/CELERY URLs para usar localhost se 'redis' não resolver mas redis estiver
if (-not (CanResolveHost 'redis')) {
    if (PortOpen 'localhost' 6379) {
        if ($env:REDIS_URL) {
            $env:REDIS_URL = $env:REDIS_URL -replace '@redis:', '@localhost:'
            $env:REDIS_URL = $env:REDIS_URL -replace '://redis:', '://localhost:'
        }
        if ($env:CELERY_BROKER_URL) {
            $env:CELERY_BROKER_URL = $env:CELERY_BROKER_URL -replace '@redis:', '@localhost:'
            $env:CELERY_BROKER_URL = $env:CELERY_BROKER_URL -replace '://redis:', '://localhost:'
        }
        if ($env:CELERY_RESULT_BACKEND) {
            $env:CELERY_RESULT_BACKEND = $env:CELERY_RESULT_BACKEND -replace '@redis:', '@localhost:'
            $env:CELERY_RESULT_BACKEND = $env:CELERY_RESULT_BACKEND -replace '://redis:', '://localhost:'
        }
        # Também expõe variáveis auxiliares usadas por alguns módulos
        if (-not $env:REDIS_HOST) { $env:REDIS_HOST = 'localhost' }
        if (-not $env:REDIS_PORT) { $env:REDIS_PORT = '6379' }
        Write-Host "Ajustado REDIS/ CELERY URLs para localhost (dev)." -ForegroundColor Yellow
    }
}

# Navegar para market_alert
Push-Location "backend/market_alert"

Write-Host "Iniciando Uvicorn..." -ForegroundColor Yellow
Write-Host "  - Host: 0.0.0.0:8000" -ForegroundColor Gray
Write-Host "  - Docs: http://localhost:8000/docs" -ForegroundColor Gray
Write-Host "  - Health: http://localhost:8000/health" -ForegroundColor Gray
Write-Host ""

# Executar Uvicorn com reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

Pop-Location
