# Dockerfile do serviço de scraping de produtos - OTIMIZADO
FROM python:3.12-slim

# Define o diretório de trabalho
WORKDIR /app

# Configura ambiente
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PIP_NO_INPUT=1

# ETAPA 1: Instalar dependências do sistema (necessárias para compilar pacotes)
# Fazer isso ANTES de copiar requirements garante que mudanças em código
# não forçam reinstalação de ferramentas do sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      gcc \
      libxml2-dev \
      libxslt1-dev \
      zlib1g-dev \
      python3-dev && \
    rm -rf /var/lib/apt/lists/*

# ETAPA 2: Instalar dependências Python (cacheado)
COPY requirements-base.txt ./
COPY backend/market_scraper/requirements-market-scraper.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-base.txt -r requirements-market-scraper.txt

# Instala navegador Chromium para fallback Playwright (Camada 3)
# Requer --shm-size=2g no docker run, ou use --disable-dev-shm-usage via env
RUN playwright install chromium --with-deps

# ETAPA 3: Copiar shared/ (dependência compartilhada entre serviços)
# Requer additional_contexts: shared_ctx: ./backend/shared no compose
COPY --from=shared_ctx . /app/shared/

# ETAPA 4: Copiar código (mudanças aqui não invalidam cache anterior)
COPY backend/market_scraper ./market_scraper
RUN mv requirements-market-scraper.txt /tmp/ 2>/dev/null || true

EXPOSE 8000

CMD ["uvicorn", "market_scraper.main:app", "--host", "0.0.0.0", "--port", "8000"]
