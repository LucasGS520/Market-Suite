#Dockerfile do serviço de scraping de produtos
FROM python:3.12-slim

#Define o diretório de trabalho da aplicação
WORKDIR /app

#Configura o caminho de módulos Python para toda a aplicação
ENV PYTHONPATH=/app

#Instalar dependências de sistema necessárias para compilar pacotes nativos
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      gcc \
      libxml2-dev \
      libxslt1-dev \
      zlib1g-dev \
      python3-dev && \
    rm -rf /var/lib/apt/lists/*

#Copia e instala as dependências do projeto
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

#Copia o código-fonte necessário seguindo regras do .dockerignore
COPY . /app/market_scraper

#Expôe a porta utilizada pelo serviço de scraping
EXPOSE 8000

#Comando padrão para iniciar o serviço de scraping
CMD ["uvicorn", "market_scraper.main:app", "--host", "0.0.0.0", "--port", "8000"]
