**Visão Geral da Stack**

- **Linguagens principais**: Python (backend, serviços assíncronos, scraping) e TypeScript/React (frontend).
- **Contêineres/orquestração local**: docker-compose.yml + `Dockerfile`s para serviços isolados.
- **Arquitetura**: backend modular (API, collectors, scrapers, workers) + serviços independentes de scraping/continuous + SPA frontend.

**Backend (responsabilidade)**

- **Python API**: Expõe endpoints REST/JSON para o frontend e opera a lógica de domínio (usuários, produtos, alertas).
- **Módulos de domínio**: coletores, comparações, notificações e orquestração de tarefas.
- **Migrations/DB**: `alembic` indica uso de ORM (SQLAlchemy) + banco relacional (PostgreSQL) para persistência.
- **Serviços assíncronos**: execução de trabalhos de scraping, comparação e envio de notificações fora do request-response sincronizado.
- **Orquestração**: controle durável do monitoramento continuo de cada produto monitorado.

**Modelo "orquestrador + executor"**
- **Plano de controle (Temporal / market_orchestrator)**: decide fluxo, temporizacao, retry/backoff e transicoes de estado.
- **Plano de execução (market_alert + Celery)**: executa coleta, comparação e notificação.

---

**Fila / Assíncrono**

- **`Celery`**: orquestra execução de tarefas assíncronas e distribuídas (workers, retries, scheduling).
- **`Redis`**: atua como broker (fila) e possivelmente como result backend/caches/locks/TTL; também usado para métricas/monitoring.

**Orquestração**

- **`Temporal`**: usado para decidir quando coletar, quando retentar, quando pausar e quando encerrar, enquanto a execucao concreta de coleta continua no ecossistema.
- **`PostgreSQL (db temporal)`**: como banco de dados separado para orquestração (não possui ligação com o banco de negócio `marketalert`)
- **`Elasticsearch`**: ainda não implementado, mas será usado para casos que criam mais do que “algumas” Workflow Executions por suportar melhor carga e otimizar performance em grandes quantidades de produtos.

**Scrapers & Workers**

- **Serviço `market_scraper`**: processo separado para coletar dados de sites (scraping), isolando dependências e carga IO.
- **`market_orchestrator`**: módulo próprio aonde será implementado orquestrador para execução contínua/infinito trabalhando 24/7 (ainda em desenvolvimento)
- **Comunicação**: scrapers enviam tarefas para Celery/Redis ou chamam API do backend conforme desenho.

**Frontend**

- **React + Vite + TypeScript**: SPA moderna para UI; `vite` para dev/build rápido.
- **TailwindCSS**: estilização utilitária.
- **Comunicação**: consome API backend via HTTP (REST/JSON), autenticação por tokens.

**Banco de Dados e Persistência**

- **Banco relacional (via Alembic/ORM)**: dados primários (usuários, produtos, histórico de preços, alertas).
- **Redis**: dados voláteis, filas, locks, rate-limits, possivelmente TTL para estados temporários.

**Observabilidade & Infra**

- **Logging**: módulo `logging_config.py` para logs estruturados.
- **Monitoramento Redis**: scripts/utilities para checar uso/métricas em `redis_monitoring`.

**Principais bibliotecas prováveis (por papel)**

- Backend: `fastapi`/`uvicorn` (ASGI), `sqlalchemy` + `alembic`, `celery`, `redis` (redis‑py), `httpx/requests` (HTTP), libs de parsing (BeautifulSoup/parsers).
- Frontend: `react`, `vite`, `typescript`, `tailwindcss`, `eslint`.

**Como tudo se comunica (fluxo simplificado)**

- Frontend → Backend: chamadas HTTP/REST para obter dados, autenticação e ações do usuário.
- Backend → Banco: ORM (SQLAlchemy) para leitura/gravação transacional.
- Backend/Scraper → Celery (via Redis): enfileiramento de tarefas de scraping, processamento e notificações.
- Workers (Celery) → Backend/DB: gravam resultados, atualizam histórico e disparam notificações.
- Docker Compose conecta/isol a rede entre containers (API, workers, Redis, Postgres).
