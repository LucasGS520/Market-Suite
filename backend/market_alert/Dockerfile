# Dockerfile da API principal do MarketAlert - OTIMIZADO
FROM python:3.11-slim

# Define diretório de trabalho
WORKDIR /market_alert

# PYTHONPATH para imports relativos
ENV PYTHONPATH=/market_alert \
    PYTHONUNBUFFERED=1 \
    PIP_NO_INPUT=1

# ETAPA 1: Instalar dependências (este layer é cacheado)
# Mudanças em código não invalidam este cache
COPY requirements-base.txt ./
COPY backend/market_alert/requirements-market-alert.txt .

# Usar BuildKit cache para pip (evita redownload)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-base.txt -r requirements-market-alert.txt

# ETAPA 2: Copiar shared/ (dependência compartilhada entre serviços)
# Requer additional_contexts: shared_ctx: ./backend/shared no compose
COPY --from=shared_ctx . ./shared/

# ETAPA 3: Copiar código (mudanças aqui não afetam layer anterior)
COPY backend/market_alert ./market_alert/

EXPOSE 8000

CMD ["uvicorn", "market_alert.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
