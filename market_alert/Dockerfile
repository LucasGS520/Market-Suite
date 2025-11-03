#Dockerfile da API principal do MarketAlert
FROM python:3.11-slim

#Define diretório de trabalho dentro do container
WORKDIR /market_alert

# Garante que o diretório da aplicação esteja no PYTHONPATH para imports relativos
ENV PYTHONPATH=/market_alert

#Copia apenas as dependencias e instala
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

#Copia o código fonte necessário conforme regras do .dockerignore
COPY . .

#Exponha a porta utilizada pelo serviço
EXPOSE 8000

#Comando padrão para inciar a API FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
