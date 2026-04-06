#!/usr/bin/env bash
# load_env.sh - Carrega os arquivos de ambiente corretos por ambiente.
#
# Uso: bash scripts/load_env.sh <ambiente>
#   Ambientes validos: development, staging, production
#
# Comandos oficiais:
#   - Dev:     bash scripts/load_env.sh development
#   - Hml:     bash scripts/load_env.sh staging
#   - Prod:    bash scripts/load_env.sh production
#
# O que faz:
#   1. Copia os templates *.{ambiente} para os ativos sem sufixo lidos pelos containers.
#   2. Carimba os ativos sem sufixo como artefatos gerados.
#   3. Verifica se ha placeholders nao preenchidos em staging/production.
#   4. Gera exatamente os ativos consumidos por `docker-compose.dev.yml` e `docker-compose.hml.yml`.
#
# Atencao: os ativos sem sufixo (.env.common, .env.temporal, .env.market_alert, etc.)
# sao artefatos locais de execucao.
# Este script os gera a partir dos arquivos de template versionados por ambiente.
# Nao edite manualmente os ativos sem sufixo no fluxo operacional.
# Em staging/production, preencha os <PLACEHOLDERS> antes de executar.

set -euo pipefail

ENV="${1:-}"

if [[ -z "$ENV" ]]; then
  echo "Uso: bash scripts/load_env.sh <ambiente>"
  echo "  Ambientes validos: development, staging, production"
  exit 1
fi

if [[ "$ENV" != "development" && "$ENV" != "staging" && "$ENV" != "production" ]]; then
  echo "Ambiente invalido: '$ENV'. Use: development, staging, production"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ERRORS=0

copy_env() {
  local src="$1"
  local dst="$2"
  if [[ ! -f "$src" ]]; then
    echo "  [ERRO] Template nao encontrado: $src"
    ERRORS=$((ERRORS + 1))
    return
  fi
  cp "$src" "$dst"
  echo "  [OK] $src -> $dst"
}

mark_generated() {
  local src="$1"
  local dst="$2"
  local tmp
  tmp=$(mktemp)
  {
    echo "# ARTEFATO GERADO por scripts/load_env.sh"
    echo "# Fonte: $src"
    echo "# Ambiente: $ENV"
    echo "# Nao editar manualmente. Altere o template *.$ENV e gere novamente."
    echo ""
    cat "$dst"
  } > "$tmp"
  mv "$tmp" "$dst"
}

check_placeholders() {
  local file="$1"
  local count
  count=$(grep -c "<.*>" "$file" 2>/dev/null || true)
  if [[ "$count" -gt 0 ]]; then
    echo "  [AVISO] $file contem $count placeholder(s) nao preenchido(s) - preencher antes de subir containers"
    if [[ "$ENV" != "development" ]]; then
      ERRORS=$((ERRORS + 1))
    fi
  fi
}

check_required_var() {
  local file="$1"
  local var="$2"
  if ! grep -Eq "^${var}=.+" "$file" 2>/dev/null; then
    echo "  [ERRO] $var ausente ou vazio em $file"
    ERRORS=$((ERRORS + 1))
  fi
}

check_required_vars() {
  local file="$1"
  shift
  for var in "$@"; do
    check_required_var "$file" "$var"
  done
}

echo "=== Carregando ambiente: $ENV ==="
echo ""

# .env.common
copy_env "$ROOT/.env.common.$ENV" "$ROOT/.env.common"
mark_generated ".env.common.$ENV" "$ROOT/.env.common"
check_placeholders "$ROOT/.env.common"

# .env.temporal
copy_env "$ROOT/.env.temporal.$ENV" "$ROOT/.env.temporal"
mark_generated ".env.temporal.$ENV" "$ROOT/.env.temporal"
check_placeholders "$ROOT/.env.temporal"

# market_alert
copy_env "$ROOT/backend/market_alert/.env.market_alert.$ENV" "$ROOT/backend/market_alert/.env.market_alert"
mark_generated "backend/market_alert/.env.market_alert.$ENV" "$ROOT/backend/market_alert/.env.market_alert"
check_placeholders "$ROOT/backend/market_alert/.env.market_alert"

# market_scraper
copy_env "$ROOT/backend/market_scraper/.env.market_scraper.$ENV" "$ROOT/backend/market_scraper/.env.market_scraper"
mark_generated "backend/market_scraper/.env.market_scraper.$ENV" "$ROOT/backend/market_scraper/.env.market_scraper"
check_placeholders "$ROOT/backend/market_scraper/.env.market_scraper"

# market_orchestrator
copy_env "$ROOT/backend/market_orchestrator/.env.market_orchestrator.$ENV" "$ROOT/backend/market_orchestrator/.env.market_orchestrator"
mark_generated "backend/market_orchestrator/.env.market_orchestrator.$ENV" "$ROOT/backend/market_orchestrator/.env.market_orchestrator"
check_placeholders "$ROOT/backend/market_orchestrator/.env.market_orchestrator"

# frontend
copy_env "$ROOT/frontend/.env.frontend.$ENV" "$ROOT/frontend/.env.frontend"
mark_generated "frontend/.env.frontend.$ENV" "$ROOT/frontend/.env.frontend"
check_placeholders "$ROOT/frontend/.env.frontend"

echo ""
echo "=== Validando contrato minimo: $ENV ==="

check_required_vars "$ROOT/.env.common" \
  REDIS_HOST REDIS_PORT REDIS_PASSWORD REDIS_URL \
  CELERY_BROKER_URL CELERY_RESULT_BACKEND \
  SLACK_WEBHOOK_URL SMTP_HOST SMTP_USERNAME SMTP_PASSWORD \
  TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN FCM_SERVER_KEY \
  SECRET_KEY TEMPORAL_ADDRESS TEMPORAL_HOST TEMPORAL_PORT TEMPORAL_NAMESPACE

check_required_vars "$ROOT/.env.temporal" \
  POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB POSTGRES_PWD POSTGRES_SEEDS DB_PORT

check_required_vars "$ROOT/backend/market_alert/.env.market_alert" \
  POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB DATABASE_URL \
  FRONTEND_ORIGINS SCRAPER_SERVICE_URL TEMPORAL_ORCHESTRATION_ENABLED

check_required_vars "$ROOT/backend/market_scraper/.env.market_scraper" \
  SCRAPER_CACHE_TTL_SECONDS SCRAPER_PIPELINE_TIMEOUT_SECONDS \
  SCRAPER_HTTP_RETRIES MAX_RESPONSE_BYTES

check_required_vars "$ROOT/backend/market_orchestrator/.env.market_orchestrator" \
  DATABASE_URL TEMPORAL_TASK_QUEUE POSTGRES_HOST POSTGRES_PORT \
  TEMPORAL_DB_SSLMODE TEMPORAL_DATABASE_URL

check_required_vars "$ROOT/frontend/.env.frontend" VITE_API_URL

echo ""
if [[ $ERRORS -gt 0 ]]; then
  echo "X $ERRORS problema(s) encontrado(s). Corrija antes de subir os containers."
  exit 1
else
  echo "OK Ambiente '$ENV' carregado com sucesso."
fi
