#Dockerfle do serviço de scraping de produtos
FROM python:3.12-slim

#Define o diretório de trabalho da aplicação
WORKDIR /market_scraper

#Copia e instala as dependências do projeto
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

#Copia o código-fonte necessário seguindo regras do .dockerignore
COPY . .

#Comando padrão para iniciar o serviço de scraping
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
