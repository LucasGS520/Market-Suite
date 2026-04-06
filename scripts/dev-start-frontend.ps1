# dev-start-frontend.ps1
# Inicia servidor Vite de desenvolvimento para o frontend
# Uso: .\scripts\dev-start-frontend.ps1

Write-Host "=== Iniciando Frontend (Vite) ===" -ForegroundColor Cyan
Write-Host ""

# Verificar se pnpm está instalado
if ((Get-Command pnpm -ErrorAction SilentlyContinue) -eq $null) {
    Write-Host "Instalando pnpm..." -ForegroundColor Yellow
    npm install -g pnpm
}

# Navegar para frontend
Push-Location "frontend"

# Verificar se node_modules existe
if (-not (Test-Path "node_modules")) {
    Write-Host "Instalando dependências do frontend..." -ForegroundColor Yellow
    pnpm install
}

Write-Host "Iniciando Vite dev server..." -ForegroundColor Yellow
Write-Host "  - Acesso: http://localhost:5173" -ForegroundColor Gray
Write-Host "  - API: http://localhost:8000" -ForegroundColor Gray
Write-Host ""

# Executar Vite
pnpm dev

Pop-Location
