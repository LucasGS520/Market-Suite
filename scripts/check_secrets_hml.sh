#!/usr/bin/env bash
# check_secrets_hml.sh - Valida presenca de segredos antes de subir containers em homologacao.
# Uso: bash scripts/check_secrets_hml.sh
# Fluxo oficial:
#   1. `bash scripts/load_env.sh staging`
#   2. `bash scripts/check_secrets_hml.sh`
#   3. `docker compose -f docker-compose.hml.yml up -d`
# Deve ser executado na raiz do projeto na VPS.

set -euo pipefail

ERRORS=0

check_file_exists() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "  [ERRO] Arquivo obrigatorio ausente: $file"
    ERRORS=$((ERRORS + 1))
    return 1
  fi
  return 0
}

check_var() {
  local file="$1"
  local var="$2"
  if ! grep -q "^${var}=.\+" "$file" 2>/dev/null; then
    echo "  [ERRO] $var ausente ou vazio em $file"
    ERRORS=$((ERRORS + 1))
  fi
}

check_no_placeholder() {
  local file="$1"
  local var="$2"
  local value
  value=$(grep "^${var}=" "$file" 2>/dev/null | cut -d= -f2-)
  if grep -Eq '<[^>]+>' <<<"$value"; then
    echo "  [ERRO] $var ainda contem placeholder em $file"
    ERRORS=$((ERRORS + 1))
  fi
}

check_file_placeholders() {
  local file="$1"
  local count
  count=$(grep -c "<.*>" "$file" 2>/dev/null || true)
  if [[ "$count" -gt 0 ]]; then
    echo "  [ERRO] $file ainda contem $count placeholder(s) nao preenchido(s)"
    ERRORS=$((ERRORS + 1))
  fi
}

check_required_vars() {
  local file="$1"
  shift
  for var in "$@"; do
    check_var "$file" "$var"
    check_no_placeholder "$file" "$var"
  done
}

echo "=== Validacao de segredos para homologacao ==="
echo ""

# --- .env.common ---
FILE=".env.common"
echo "Verificando $FILE..."
if check_file_exists "$FILE"; then
  check_required_vars "$FILE" \
    REDIS_HOST REDIS_PORT REDIS_PASSWORD REDIS_URL \
    CELERY_BROKER_URL CELERY_RESULT_BACKEND \
    SLACK_WEBHOOK_URL SMTP_HOST SMTP_USERNAME SMTP_PASSWORD \
    TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN FCM_SERVER_KEY \
    SECRET_KEY TEMPORAL_ADDRESS TEMPORAL_HOST TEMPORAL_PORT TEMPORAL_NAMESPACE
  check_file_placeholders "$FILE"
fi

# --- .env.temporal ---
FILE=".env.temporal"
echo "Verificando $FILE..."
if check_file_exists "$FILE"; then
  check_required_vars "$FILE" \
    POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB POSTGRES_PWD POSTGRES_SEEDS DB_PORT
  check_file_placeholders "$FILE"
fi

# --- .env.market_alert ---
FILE="backend/market_alert/.env.market_alert"
echo "Verificando $FILE..."
if check_file_exists "$FILE"; then
  check_required_vars "$FILE" \
    POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB DATABASE_URL \
    FRONTEND_ORIGINS SCRAPER_SERVICE_URL TEMPORAL_ORCHESTRATION_ENABLED
  check_file_placeholders "$FILE"
fi

# --- .env.market_orchestrator ---
FILE="backend/market_orchestrator/.env.market_orchestrator"
echo "Verificando $FILE..."
if check_file_exists "$FILE"; then
  check_required_vars "$FILE" \
    DATABASE_URL TEMPORAL_TASK_QUEUE POSTGRES_HOST POSTGRES_PORT \
    TEMPORAL_DB_SSLMODE TEMPORAL_DATABASE_URL
  check_file_placeholders "$FILE"
fi

# --- .env.market_scraper ---
FILE="backend/market_scraper/.env.market_scraper"
echo "Verificando $FILE..."
if check_file_exists "$FILE"; then
  check_required_vars "$FILE" \
    SCRAPER_CACHE_TTL_SECONDS SCRAPER_PIPELINE_TIMEOUT_SECONDS \
    SCRAPER_HTTP_RETRIES MAX_RESPONSE_BYTES
  check_file_placeholders "$FILE"
fi

echo ""
if [[ $ERRORS -gt 0 ]]; then
  echo "X $ERRORS problema(s) encontrado(s). Corrija antes de subir os containers."
  exit 1
else
  echo "OK Todos os segredos verificados. Pode prosseguir com o deploy."
  exit 0
fi
