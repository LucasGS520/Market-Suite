#Imagem oficial Pyhton leve
FROM python:3.11-slim

#Define diretório de trabalho no container
WORKDIR /app

#Copia só as dependencias e instala
COPY ../requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir playwright
RUN playwright install --with-deps chromium

COPY beat_with_metrics.py /app/beat_with_metrics.py

#copia todo o codigo da aplicação
COPY . .

#Documenta a porta que o container vai usar
EXPOSE 8000

#Comando padrão ao iniciar o container
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
