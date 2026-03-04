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
COPY --from=root requirements-base.txt ./
COPY requirements-market-scraper.txt ./

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-base.txt -r requirements-market-scraper.txt

# ETAPA 3: Copiar código (mudanças aqui não invalidam cache anterior)
COPY . /app/market_scraper

EXPOSE 8000

CMD ["uvicorn", "market_scraper.main:app", "--host", "0.0.0.0", "--port", "8000"]
