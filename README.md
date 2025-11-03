# Market Suite
Market Suite é uma suíte de monitoramento de preços composta por serviços independentes que compartilham contratos, métricas e ferramentas de infraestrutura. A plataforma combina API pública, processamento assíncrono e um microserviço de scraping especializado, permitindo acompanhar produtos, comparar ofertas e disparar alertas quando critérios de preço são atendidos.

## Serviços e responsabilidades

| Serviço | Função principal | Documentação dedicada |
|---------|------------------|-----------------------|
| **market_alert** | expõe a API pública, agenda tarefas Celery, persiste dados, consome o scraper via cliente dedicado e orquestra notificações | [`market_alert/README.md`](market_alert/README.md) |
| **market_scraper** | valida URLs, realiza o download da página, executa o pipeline de parsing e devolve um `ParserResponse`. | [`market_scraper/README.md`](market_scraper/README.md) |
| **shared** | concentra contratos, métricas, configuração e utilidades comuns às duas aplicações. | [`shared/`](shared/) |

O arquivo [`docker-compose.yml`](docker-compose.yml) oferece a topologia completa com banco de dados PostgreSQL, Redis, workers Celery, infraestrutura de observabilidade (Prometheus, Alertmanager, Grafana, Loki, Promtail) e ferramentas auxiliares como Locust.

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
3. Quando um produto precisa ser atualizado, o `market_alert` chama `POST /scraper/parse` no `market_scraper` usando contratos de [`shared/schemas/schemas_scraper.py`](shared/schemas/schemas_scraper.py), onde `source` é o campo canônico (aceitando alias `marketplace` apenas para compatibilidade).
4. O `market_scraper` aplica validação de URL, checagem de `robots.txt`, cache com LRU/TTL e executa o pipeline sequencial (`FetchHTML` → `DomainSpecificParser` → `JsonLdParser` → `HtmlMetadataParser` → `GenericFallbackParser`).
5. Os workers Celery persistem resultados, atualizam métricas (`shared/metrics/`) e publicam notificações quando as regras de alerta ativas são atendidas.
6. Métricas e logs são expostos para observabilidade centralizada; dashboards prontos ficam disponíveis no Grafana.

### Princípios de integração
- **Contrato único:** residem em [`shared/schemas/schemas_scraper.py`](shared/schemas/schemas_scraper.py) e são reutilizados pela API, worker e scraper.
- **Isolamento de parsing:** apenas o `market_scraper` manipula HTML e heurísticas de extração; o `market_alert` utiliza somente os dados consolidados.
- **Chamada HTTP:** o `market_alert` usa `ScraperClient` (`market_alert/services/scraper_client.py`) para enviar `POST /scraper/parse` ao `market_scraper`.
- **Tratamento de erros:** respostas `304 Not Modified` ou `no_result` evitam persistir dados desnecessários; erros são registrados em `crud_errors` com métricas específicas.
- **Idempotência e cache:** o scraper evita downloads duplicados (singleflight + cache) e devolve `304 Not Modified`/`no_result` quando não há novidade, reduzindo carga no banco e no pipeline.
- **Sem parsing duplicado:** apenas o `market_scraper` manipula HTML. Caso novos campos sejam necessários, evolua primeiro `shared/` e ajuste o pipeline do scraper antes de tocar no domínio de alertas.
- **Observabilidade compartilhada:** métricas, logs e configurações sensíveis seguem convenções unificadas em `shared/` para simplificar automações.

## Executando a Suíte

### Docker Compose
```bash
docker compose up -d db redis redis-init
docker compose up -d api market_scraper celery-worker celery_beat
```
Interrompa com `docker compose down`. Variáveis comuns residem em `.env.common`, enquanto configurações específicas ficam em `market_alert/.env.market_alert` e `market_scraper/.env.market_scraper`.

### Ambiente local
1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. Configure as variáveis de ambiente (.env descritos acima).
4. Inicie os serviços desejados:
   - API FastAPI: `uvicorn market_alert.main:app --reload --port 8000`
   - Worker Celery: `celery -A market_alert.core.celery_app:celery_app worker --loglevel=info --pool=threads --concurrency=4 -Q celery,scraping,monitor`
   - Celery Beat com métricas: `python market_alert/beat_with_metrics.py`
   - Scraper FastAPI: `uvicorn market_scraper.main:app --reload --port 8010`

## Observabilidade e operação
- **Métricas Prometheus:** `/metrics` em cada serviço (API `:8000`, Beat `:8001`, Worker `:8002`, Scraper `:8010`). As definições vivem em [`shared/metrics`](shared/metrics).
- **Logs estruturados:** os serviços usam `structlog` e enviam JSON para stdout; com Compose, Loki + Promtail coletam os fluxos.
- **Dashboards:** Grafana em `http://localhost:3000` já provisiona dashboards básicos (ver `shared/infra/monitoring`).
- **Alertas:** Alertmanager (`:9093`) utiliza regras em `shared/infra/alertmanager` e pode ser integrado a canais externos.

## Estrutura do Repositório
```text
market_alert/      # API FastAPI, tasks Celery, notificações e rotinas de comparação
market_scraper/    # Microserviço FastAPI de scraping com pipeline sequencial
shared/            # Configuração, contratos, métricas, utilidades e recursos de infraestrutura
docker-compose.yml # Orquestração completa em desenvolvimento
requirements.txt   # Dependências comuns (FastAPI, Celery, httpx, structlog, etc.)
```

## Testes e qualidade
- Execute `pytest market_alert -q` para validar a API, tasks e integrações.
- Execute `pytest market_scraper -q` para validar parsers, utilitários e pipeline.
- Testes compartilhados (ex.: contratos) estão em `shared/tests`.
- Linters e validações adicionais podem ser configurados via `pre-commit` conforme a equipe necessitar.

## Próximos passos e referências
- Leia [`AGENTS.md`](AGENTS.md) para instruções operacionais direcionadas a agentes/automação.
- Consulte os READMEs específicos para detalhes de cada serviço.
- Atualize este documento sempre que novos serviços, filas ou integrações forem introduzidos na suíte.
