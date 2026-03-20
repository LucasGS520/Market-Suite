# Dockerfile do market_orchestrator — Temporal Worker
FROM python:3.11-slim

WORKDIR /backend

ENV PYTHONPATH=/backend \
    PYTHONUNBUFFERED=1 \
    PIP_NO_INPUT=1

# Instalar dependências (layer cacheado separado do código)
COPY requirements-orchestrator.txt ./

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-orchestrator.txt

# Copiar código do módulo
COPY . ./market_orchestrator/

CMD ["python", "-m", "market_orchestrator.worker"]
