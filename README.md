# Market Suite
Market Suite é uma suíte de monitoramento de preços composta por serviços independentes que compartilham contratos, métricas e ferramentas de infraestrutura. A plataforma combina API pública, processamento assíncrono e um microserviço de scraping especializado, permitindo acompanhar produtos, comparar ofertas e disparar alertas quando critérios de preço são atendidos.

## Serviços e responsabilidades
O repositório está organizado em dois blocos principais: `frontend/` e `backend/`. O módulo `backend/` passou a englobar todos os serviços Python que anteriormente ficavam na raiz, preservando a separação lógica entre API, scraper e utilidades compartilhadas, porém com uma hierarquia única que facilita automação, importações relativas e distribuição em contêineres.

| Serviço | Função principal | Documentação dedicada |
|---------|------------------|-----------------------|
| **backend/market_alert** | expõe a API pública, agenda tarefas Celery, persiste dados, consome o scraper via cliente dedicado e orquestra notificações | [`backend/market_alert/README.md`](backend/market_alert/README.md) |
| **backend/market_scraper** | valida URLs, realiza o download da página, executa o pipeline de parsing e devolve um `ParserResponse`. | [`backend/market_scraper/README.md`](backend/market_scraper/README.md) |
| **backend/shared** | concentra contratos, métricas, configuração e utilidades comuns às duas aplicações backend. | [`backend/shared/`](backend/shared/) |
| **frontend** | provê a interface web responsiva utilizada para configurar monitoramentos, acompanhar produtos, visualizar alertas e gerenciar credenciais. | [`frontend/`](frontend/) |

O arquivo [`docker-compose.yml`](docker-compose.yml) oferece a topologia completa com banco de dados PostgreSQL, Redis, workers Celery, infraestrutura de observabilidade (Prometheus, Alertmanager, Grafana, Loki, Promtail) e ferramentas auxiliares como Locust. Serviços Node do frontend podem ser incluídos no Compose conforme evoluirmos a automação.

## Visão Arquitetural
```mermaid
graph TD
    User[Usuário autenticado] --> API[market_alert]
    API --> |HTTP (ParserRequest) | Scraper[market_scraper]
    API --> |Filas Celery | Worker[Celery Worker]
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
```

### Fluxo Ponta a Ponta
1. Usuários interagem apenas com o `market_alert`, autenticando via rotas de auth e configurando monitoramentos.
2. A API agenda tarefas Celery (`monitor`, `scraping`, `metrics`) e dispara coleta imediata quando necessário.
3. Quando um produto precisa ser atualizado, o `market_alert` chama `POST /scraper/parse` no `market_scraper` usando contratos de [`backend/shared/schemas/schemas_scraper.py`](backend/shared/schemas/schemas_scraper.py), onde `source` é o campo canônico (aceitando alias `marketplace` apenas para compatibilidade).
4. O `market_scraper` aplica validação de URL, checagem de `robots.txt`, cache com LRU/TTL e executa o pipeline sequencial (`FetchHTML` → `DomainSpecificParser` → `JsonLdParser` → `HtmlMetadataParser` → `GenericFallbackParser`).
5. Os workers Celery persistem resultados, atualizam métricas (`backend/shared/metrics/`) e publicam notificações quando as regras de alerta ativas são atendidas.
6. Métricas e logs são expostos para observabilidade centralizada; dashboards prontos ficam disponíveis no Grafana.

### Princípios de integração
- **Contrato único:** residem em [`backend/shared/schemas/schemas_scraper.py`](backend/shared/schemas/schemas_scraper.py) e são reutilizados pela API, worker e scraper.
- **Isolamento de parsing:** apenas o `market_scraper` manipula HTML e heurísticas de extração; o `market_alert` utiliza somente os dados consolidados.
- **Chamada HTTP:** o `market_alert` usa `ScraperClient` (`backend/market_alert/services/scraper_client.py`) para enviar `POST /scraper/parse` ao `market_scraper`.
- **Tratamento de erros:** respostas `304 Not Modified` ou `no_result` evitam persistir dados desnecessários; erros são registrados em `crud_errors` com métricas específicas.
- **Idempotência e cache:** o scraper evita downloads duplicados (singleflight + cache) e devolve `304 Not Modified`/`no_result` quando não há novidade, reduzindo carga no banco e no pipeline.
- **Sem parsing duplicado:** apenas o `market_scraper` manipula HTML. Caso novos campos sejam necessários, evolua primeiro `backend/shared/` e ajuste o pipeline do scraper antes de tocar no domínio de alertas.
- **Observabilidade compartilhada:** métricas, logs e configurações sensíveis seguem convenções unificadas em `backend/shared/` para simplificar automações.
## Executando a Suíte

### Docker Compose
```bash
docker compose up -d db redis redis-init
docker compose up -d api market_scraper celery-worker celery_beat
```
Interrompa com `docker compose down`. Variáveis comuns residem em `.env.common`, enquanto configurações específicas ficam em `backend/market_alert/.env.market_alert` e `backend/market_scraper/.env.market_scraper`.


### Ambiente local
1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. Configure as variáveis de ambiente (.env descritos acima).
4. Inicie os serviços desejados:
   - API FastAPI: `uvicorn backend.market_alert.main:app --reload --port 8000`
   - Worker Celery: `celery -A backend.market_alert.core.celery_app:celery_app worker --loglevel=info --pool=threads --concurrency=4 -Q celery,scraping,monitor`
   - Celery Beat com métricas: `python backend/market_alert/beat_with_metrics.py`
   - Scraper FastAPI: `uvicorn backend.market_scraper.main:app --reload --port 8010`

## Frontend atual
O frontend é uma aplicação React 18 construída com Vite e TypeScript, estilizada com Tailwind CSS e componentes Radix UI. O projeto utiliza `@tanstack/react-query` para gerenciamento de cache de requisições, `react-hook-form` para formulários e `zod` para validação. 
Durante o desenvolvimento, o servidor de desenvolvimento Vite expõe a aplicação em `http://localhost:5173` e o pacote inclui um servidor Express (`frontend/server/index.ts`) que empacota os artefatos estáticos para execução em produção.

Principais fluxos suportados pela interface:
- Autenticação JWT e gerenciamento de sessão via `AuthContext`, permitindo acesso às rotas protegidas.
- Cadastro de produtos monitorados, visualização de concorrentes e disparo manual de coletas com feedback em tempo real.
- Painel de alertas e dashboard com indicadores consolidados, utilizando componentes responsivos baseados em Radix UI.
- Configurações de perfil e preferências de tema com persistência em armazenamento local.

Comandos úteis:
```bash
cd frontend
pnpm install
pnpm dev        # inicia o Vite em modo desenvolvimento
pnpm build      # gera artefatos estáticos e bundle do servidor Express
pnpm start      # executa o servidor Express usando os arquivos de produção
```

## Integração frontend ⇄ backend
A comunicação entre frontend e backend ocorre via HTTP usando o cliente definido em [`frontend/client/src/lib/api.ts`](frontend/client/src/lib/api.ts). 
A URL base é configurável pela variável `VITE_FRONTEND_FORGE_API_URL`, com fallback para `http://localhost:8000/`, mantendo alinhamento com o serviço `backend/market_alert` em desenvolvimento local. Fluxos autenticados armazenam o token JWT no `localStorage` e reaproveitam o endpoint `/users/me` para restaurar a sessão.

Atualmente, a integração cobre os cenários de autenticação, listagem/cadastro de produtos monitorados e consulta de concorrentes, utilizando as rotas já estáveis da API. 
Rotas voltadas a métricas avançadas e notificações em tempo real ainda utilizam dados simulados em componentes específicos até que endpoints dedicados estejam disponíveis. 
O frontend permanece funcional de forma isolada com mocks para fins de demonstração, enquanto o backend continua operando com a API e os workers mesmo sem a interface web.


## Observabilidade e operação
- **Métricas Prometheus:** `/metrics` em cada serviço (API `:8000`, Beat `:8001`, Worker `:8002`, Scraper `:8010`). As definições vivem em [`backend/shared/metrics`](backend/shared/metrics).
- **Logs estruturados:** os serviços usam `structlog` e enviam JSON para stdout; com Compose, Loki + Promtail coletam os fluxos.
- **Dashboards:** Grafana em `http://localhost:3000` já provisiona dashboards básicos (ver `backend/shared/infra/monitoring`).
- **Alertas:** Alertmanager (`:9093`) utiliza regras em `backend/shared/infra/alertmanager` e pode ser integrado a canais externos.

## Estrutura do Repositório
```text
backend/
  market_alert/    # API FastAPI, tasks Celery, notificações e rotinas de comparação
  market_scraper/  # Microserviço FastAPI de scraping com pipeline sequencial
  shared/          # Configuração, contratos, métricas, utilidades e recursos de infraestrutura
frontend/          # Aplicação React + Vite com servidor Express para distribuição
docker-compose.yml # Orquestração completa em desenvolvimento
requirements.txt   # Dependências comuns aos serviços Python
```

## Testes e qualidade
- Execute `pytest backend/market_alert -q` para validar a API, tasks e integrações.
- Execute `pytest backend/market_scraper -q` para validar parsers, utilitários e pipeline.
- Testes compartilhados (ex.: contratos) estão em `backend/shared/tests`.
- Linters e validações adicionais podem ser configurados via `pre-commit` conforme a equipe necessitar.

## Próximos passos e referências
- Leia [`AGENTS.md`](AGENTS.md) para instruções operacionais direcionadas a agentes/automação.
- Consulte os READMEs específicos para detalhes de cada serviço.
- Atualize este documento sempre que novos serviços, filas ou integrações forem introduzidos na suíte.
