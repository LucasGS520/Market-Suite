#Imagem base com Python
FROM python:3.12-slim

#Define o diretório de trabalho
WORKDIR /app

#Copia e instala as dependências do projeto
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

#Copia o código-fonte para o container
COPY . .

#Comando padrão para iniciar a aplicação
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
