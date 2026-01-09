# Market Suite
Market Suite é uma suíte de monitoramento de preços composta por dois grandes módulos — `backend/` e `frontend/` — apoiados por infraestrutura compartilhada de dados, mensageria e observabilidade. 
A plataforma combina API pública, processamento assíncrono e microserviço de scraping especializado, permitindo acompanhar produtos e comparar ofertas.

## Serviços e responsabilidades
A suíte é organizada em duas camadas principais:

- **Backend**: engloba API, workers Celery, microserviço de scraping e utilidades compartilhadas em Python. Cada serviço roda em contêiner próprio, mas compartilha contratos, métricas e convenções em `backend/shared/`.
- **Frontend**: aplicação React + Vite que consome a API pública, oferece interface responsiva para configurar monitoramentos e consolida indicadores operacionais.

## Visão Arquitetural
```mermaid
graph TD
    User[Usuário Autenticado] --> FE[Frontend React]
    FE --> |HTTP/JSON| API[market_alert]
    API --> |HTTP (ParserRequest)| Scraper[market_scraper]
    API --> |Filas Celery| Worker[Celery Worker]
    Worker --> Beat[Celery Beat]
    API --> DB[(PostgreSQL)]
    Worker --> DB
    API --> Cache[(Redis)]
    Worker --> Cache
    API --> Prometheus
    Worker --> Prometheus
    Beat --> Prometheus
    Scraper --> Prometheus
    Prometheus --> Grafana[(Dashboards)]
    API --> Loki[(Logs estruturados)]
    Worker --> Loki
    Scraper --> Loki
    FE --> |Build estático| CDN[(Servidor Express/Vite)]
```

## Backend 
### Arquitetura do backend
O módulo `backend/` concentra serviços Python que antes viviam na raiz do repositório. A organização atual favorece automação, importações relativas e distribuição em contêineres.

| Serviço | Função principal | Documentação dedicada |
|---------|------------------|-----------------------|
| **backend/market_alert** | expõe a API pública FastAPI, agenda tarefas Celery, persiste dados em PostgreSQL e consome o scraper via cliente dedicado | [`backend/market_alert/README.md`](backend/market_alert/README.md) |
| **backend/market_scraper** | valida URLs, realiza download das páginas, executa pipeline de parsing multiestágio e devolve `ParserResponse` | [`backend/market_scraper/README.md`](backend/market_scraper/README.md) |
| **backend/shared** | reúne contratos Pydantic, métricas, configuração, clientes externos e utilidades comuns | [`backend/shared/`](backend/shared/) |

> Nota operacional: a inferência de disponibilidade agora antecede a validação do parser e preserva `last_status` informado pelo scraper. A listagem `GET /monitored/` também exibe itens sem preço coletado para sinalizar anúncios pausados ou indisponíveis.

#### Fluxo interno do backend
1. **Autenticação e entrada de requisições**: o `market_alert` recebe chamadas HTTP, autentica usuários via JWT e valida payloads com esquemas de `backend/shared/schemas`.
2. **Orquestração de tarefas**: operações que exigem processamento assíncrono geram tasks Celery (`collect_product_task`, `collect_competitor_task`, `compare_prices_task`) enfileiradas no Redis.
3. **Coleta de dados**: tasks que demandam scraping invocam o `ScraperClient` (`backend/market_alert/services/scraper_client.py`), enviando `POST /scraper/parse` ao `market_scraper`.
4. **Pipeline de scraping**: o `market_scraper` executa validação de URL, checagem de `robots.txt`, caching LRU com TTL e pipeline sequencial (`FetchHTML` → `DomainSpecificParser` → `JsonLdParser` → `HtmlMetadataParser` → `GenericFallbackParser`). Resultados são devolvidos como `ParserResponse`.
   - O contrato do `ParserResponse` expõe sempre `price|currency` (admite `null`), `availability`/`last_status` e cabeçalhos (`etag`, `not_modified`) para sinalizar indisponibilidade sem gravar preços `0.00`.
5. **Persistência e regras de negócio**: workers Celery consolidam dados no PostgreSQL (`backend/market_alert/repositories`), recalculam comparações e armazenam histórico de coletas.
6. **Eventos e notificações**: eventos de domínio são persistidos em `event_log`, avaliados por regras configuráveis e geram notificações com idempotência, retries e auditoria.
7. **Observabilidade e resiliência**: cada serviço publica métricas Prometheus, logs estruturados e incrementa contadores de erro. O fluxo atual privilegia simplicidade: as regras de retry permanecem, mas a idempotência distribuída foi desativada nas rotas manuais para facilitar depuração.

### Tarefas Celery do `market_alert`
- **Collector (`tasks.collector_product_task.collect_product_task`)**: executa scraping de um monitorado ou concorrente por vez, respeitando lock Redis (`acquire_product_lock`) antes de chamar o scraper. Retorna `ScrapeResult` padronizado com status (`success`, `not_modified`, `no_result`, `error`), `http_status`, sinalização de mudança de preço/disponibilidade e `error_code` quando existir.
- **Agendador de rechecagem (`tasks.recheck_scheduler_task.schedule_rechecks`)**: Beat que varre monitorados com `next_check_at` vencido, recalcula o próximo horário com base em `check_interval` (ou `RECHECK_INTERVAL_DEFAULT`) e enfileira diretamente a `collect_product_task` com jitter controlado.
- **Comparação (`tasks.compare_prices_task.compare_prices_task`)**: permanece idempotente e leve, usada pelo collector e acionamentos manuais para recalcular históricos e campos derivados.
- **Notificações (`fila notifications`)**: entrega alertas enfileirados com retry e backoff, registrando histórico em `notification_attempt` e marcando DLQ quando necessário.

#### Princípios do backend
- **Exposição de APIs**: o FastAPI em `market_alert` oferece rotas públicas, autenticação JWT e endpoints para monitoramentos, concorrentes e comparações.
- **Contrato único**: esquemas em `backend/shared/schemas/schemas_scraper.py` padronizam comunicação API ↔ scraper.
- **Separação de responsabilidades**: apenas o `market_scraper` processa HTML, enquanto o `market_alert` persiste dados e aplica lógica de negócios.
- **Processamento assíncrono**: workers Celery e Beat ficam no mesmo pacote, reutilizando `backend/shared/core` para inicialização, métricas e observabilidade.
- **Simplicidade operacional**: priorizamos contratos previsíveis, removendo idempotência distribuída nos disparos manuais.
- **Extensibilidade controlada**: novos marketplaces exigem evoluções no `market_scraper` e nos contratos compartilhados antes de tocar fluxos críticos.
- **Biblioteca compartilhada**: `backend/shared` concentra schemas Pydantic, utilidades, métricas, observabilidade e integrações externas consumidas pelos demais serviços.

## Frontend
### Arquitetura do frontend
O módulo `frontend/` entrega a interface web que interage com o backend.

| Componente | Responsabilidade |
|------------|------------------|
| **Aplicação React 18** (`frontend/src/`) | constrói telas, gerencia rotas e estado global via Context API e `@tanstack/react-query` |
| **Camada de API** (`frontend/src/lib/api.ts`) | centraliza chamadas HTTP, tratamento de erros e renovação de tokens |
| **Servidor Express** (`frontend/server/index.ts`) | serve os artefatos estáticos gerados pelo Vite em ambientes de produção |

#### Fluxo interno do frontend
1. **Bootstrap**: o Vite carrega a aplicação React, inicializa `AuthContext` e tenta renovar sessão via `/auth/refresh` usando cookie HttpOnly quando disponível.
2. **Autenticação**: formulários de login geram `access_token` em memória; o refresh token fica preferencialmente em cookie HttpOnly para reduzir exposição local.
3. **Consumo de dados**: hooks do `react-query` buscam produtos monitorados, concorrentes e comparações via endpoints do backend, mantendo cache e estados de carregamento.
4. **Ações do usuário**: interações como cadastro de monitoramentos, disparo de coletas e atualização de perfil chamam serviços da API e exibem feedback em toasts/modal.
5. **Dashboard de indicadores**: com indicadores consolidados, utilizando componentes responsivos baseados em Radix UI.
6. **Observabilidade do cliente**: eventos relevantes (ex.: erros de rede, ações críticas) são enviados a provedores de logging/browser analytics quando configurados.

#### Princípios do frontend
- **UX responsiva**: componentes baseados em Radix UI e Tailwind garantem adaptação a diferentes dispositivos.
- **Sincronização de estado**: `react-query` evita chamadas duplicadas e trata revalidação automática.
- **Isolamento de mock**: a aplicação pode rodar com mocks locais para demonstração sem depender do backend, útil para testes de UI.
- **Paginação ajustável na listagem de produtos**: a tela de Produtos controla paginação no cliente, oferecendo 5/10/25 itens por página ou carregamento total (200 itens) em modo tabela; o backend apenas responde aos parâmetros `page` e `per_page` sem impor lógicas adicionais.
- **Prioridades de status e competitividade**: anúncios indisponíveis são tratados como `Inativo` (incluindo sinais em `last_status`), `Pausado` só aparece quando o monitoramento foi suspenso manualmente com anúncio disponível e estados competitivos (`Competitivo`/`Atenção`/`Urgente`) só são exibidos quando há pelo menos um concorrente com preço. Na ausência de concorrentes, a UI exibe `Sem concorrentes`.
- **Tokens em memória**: `access_token` fica somente em memória. Para fallback sem cookie HttpOnly, configure `VITE_AUTH_REFRESH_STORAGE=cookie`.


## Integração frontend ⇄ backend
- **Protocolos**: comunicação ocorre via HTTP/JSON sobre HTTPS (em produção). O cliente padrão (`frontend/src/lib/api.ts`) injeta o token JWT no header `Authorization`.
- **Configuração de endpoints**: a variável `VITE_API_URL` define a URL base; em desenvolvimento local, o padrão é `http://localhost:8000/` (API do `market_alert`).
- **Fluxos suportados**: autenticação, verificação de email/telefone, CRUD de produtos monitorados, listagem de concorrentes, disparo manual de coletas e consulta de comparações consolidadas.
- **Tratamento de sessões**: o frontend tenta refresh ao receber `401` e reutiliza o cookie HttpOnly de refresh quando configurado.
- **CORS/credenciais**: para usar cookie HttpOnly, o backend precisa permitir `Access-Control-Allow-Credentials` e o frontend envia `credentials: include`.
- **Cookies de refresh**: parâmetros do backend são configuráveis via `REFRESH_TOKEN_COOKIE_NAME`, `REFRESH_TOKEN_COOKIE_PATH`, `REFRESH_TOKEN_COOKIE_SECURE` e `REFRESH_TOKEN_COOKIE_SAMESITE`.
- **Fallbacks**: componentes sem endpoint definitivo utilizam dados mock; a integração deve ser atualizada quando novos recursos REST forem publicados.

---

## Operação e execução do projeto

### Docker Compose
```bash
docker compose up -d db redis redis-init
docker compose up -d api market_scraper celery-worker celery-worker-notifications celery_beat
# Após dependências, subir serviços de aplicação e observabilidade
docker compose up -d api market_scraper celery-worker celery-worker-notifications celery_beat frontend grafana prometheus loki promtail
```

- Interrompa com `docker compose down` (utilize `docker compose down -v` para remover volumes, se necessário).
- Variáveis comuns residem em `.env.common`; arquivos específicos estão em `backend/market_alert/.env.market_alert`, `backend/market_scraper/.env.market_scraper` e `frontend/.env` (quando aplicável).

### Ambiente local (sem Docker)
#### Backend
1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. Configure arquivos `.env` mencionados acima.
4. Inicie serviços:
   - API FastAPI: `uvicorn backend.market_alert.main:app --reload --port 8000`
   - Worker Celery principal: `celery -A backend.market_alert.core.celery_app:celery_app worker --loglevel=info --pool=prefork --concurrency=4 -Q celery,scraping,monitor`
   - Worker Celery de notificações: `celery -A backend.market_alert.core.celery_app:celery_app worker --loglevel=info --pool=prefork --concurrency=2 -Q notifications`--pool=threads --concurrency=4 -Q celery,scraping,monitor,notifications`
   - Celery Beat com métricas: `python backend/market_alert/beat_with_metrics.py`
   - Scraper FastAPI: `uvicorn backend.market_scraper.main:app --reload --port 8010`

#### Frontend
1. `cd frontend`
2. `pnpm install`
3. `pnpm dev` para modo desenvolvimento em `http://localhost:5173`
4. `pnpm build` gera artefatos estáticos e o bundle do servidor Express
5. `pnpm start` executa o servidor Express com build de produção

## Observabilidade e operação contínua
### Backend
- **Métricas Prometheus**: endpoints `/metrics` expostos pela API (`:8000`), Beat (`:8001`), Worker (`:8002`) e Scraper (`:8010`). Métricas definidas em [`backend/shared/metrics`](backend/shared/metrics).
- **Logs estruturados**: todos os serviços usam `structlog` com saída JSON. Em Compose, Loki + Promtail coletam e disponibilizam via Grafana (`http://localhost:3000`).
- **Tracing opcional**: pontos de integração podem enviar spans para provedores OTLP quando configurado nas variáveis de ambiente.

### Frontend
- **Build health**: logs do Vite/Express ajudam a identificar falhas de build ou inicialização.
- **Métricas de uso**: integração com ferramentas de analytics pode ser habilitada via variáveis de ambiente (não obrigatória por padrão).
- **Monitoramento de erros**: configure provedores como Sentry ou LogRocket conectando hooks do React às APIs correspondentes.

## Estrutura do respositório
```text
backend/
  market_alert/    # API FastAPI, tasks Celery e rotinas de comparação
  market_scraper/  # Microserviço FastAPI de scraping com pipeline sequencial
  shared/          # Configuração, contratos, métricas, utilidades e recursos de infraestrutura
frontend/          # Aplicação React + Vite com servidor Express para distribuição
docker-compose.yml # Orquestração completa em desenvolvimento
requirements.txt   # Dependências comuns aos serviços Python
README.md          # Visão geral, operação e integração da suíte
```

## Testes e qualidade
- Execute `pytest backend/market_alert -q` para validar a API, tasks e integrações.
- Execute `pytest backend/market_scraper -q` para validar parsers, utilitários e pipeline.
- Testes compartilhados (ex.: contratos) estão em `backend/shared/tests`.
- Para o frontend, utilize `pnpm test` (quando configurado) e `pnpm lint` para validar regras de linting.
- Linters e validações adicionais podem ser integrados via `pre-commit` conforme a equipe necessitar.

## Próximos passos e referências
- Leia [`AGENTS.md`](AGENTS.md) para instruções operacionais direcionadas a agentes/automação.
- Consulte os READMEs específicos (`backend/market_alert`, `backend/market_scraper`, `frontend`) para detalhes de cada serviço.
- Atualize este documento sempre que novos serviços, filas ou integrações forem introduzidos na suíte.
