# Market Alert

## Objetivo
O `market_alert` é o orquestrador da suíte Market Suite. Ele expõe a API pública, agenda tarefas Celery, persiste dados em PostgreSQL e interpreta as respostas vindas do `market_scraper`.

### Documentação Relacionada
- Visão geral da suíte: [`README.md`](../README.md)
- Integração com o scraping: [`market_scraper/README.md`](../market_scraper/README.md)

## Responsabilidades
- Expor endpoints REST com FastAPI para cadastro de monitoramentos, concorrentes e gerenciamento de usuários.
- Agendar tarefas Celery para scraping, comparação de preços, envio de notificações e coleta de métricas.
- Persistir produtos, históricos e erros de scraping utilizando SQLAlchemy.
- Registrar métricas HTTP, Celery e banco de dados em `/metrics` para consumo pelo Prometheus.

## Fluxo de scraping
1. A rota `POST /monitored/scrape` recebe a URL do produto e demais parâmetros de monitoramento.
2. O schema de entrada utiliza modelos Pydantic da pasta `market_alert/schemas/` e mapeia para `ParserRequest` definido em [`shared/schemas/schemas_scraper.py`](../shared/schemas/schemas_scraper.py).
3. A task `collect_product_task` valida o payload, respeita a flag global de suspensão e consulta o `market_scraper` via `ScraperClient` (`market_alert/services/scraper_client.py`).
4. O resultado (`ParseResponse`) é persistido com `create_or_update_monitored_scraped` e pode acionar `compare_prices_task` quando o preço muda.
5. Erros são registrados via `crud_errors` com o tipo apropriado (`http_error`, `no_result`, `parsing_error`), alimentando métricas e relatórios.

## Estrutura principal
```text
market_alert/
├── core/               # Configuração de ambiente, Celery e integrações
├── routes/             # Endpoints FastAPI
├── schemas/            # Modelos Pydantic e contratos públicos
├── services/           # Regras de negócio (scraping, comparação, notificações)
├── tasks/              # Tarefas Celery (scraping, comparação, métricas)
├── models/ & crud/     # Mapeamentos ORM e operações de banco
├── notifications/      # Canais e templates de notificação
└── utils/              # Auxiliares diversos
```

## Executando somente o `market_alert`
1. Ative a `venv` e exporte as variáveis de ambiente:
   - `.env.common`
   - `market_alert/.env.market_alert`
2. Suba dependências externas (PostgreSQL e Redis) ou reutilize o `docker compose` do projeto.
3. Inicie a API: `uvicorn market_alert.main:app --port 8000 --reload`.
4. Em terminais separados, execute:
   - Worker: `celery -A market_alert.core.celery_app:celery_app worker --loglevel=info --pool=threads --concurrency=4 -Q celery,scraping,monitor`
   - Beat com métricas: `python market_alert/beat_with_metrics.py`

## Integração com o `market_scraper`
- O cliente HTTP está em `market_alert/services/scraper_client.py` e utiliza os contratos compartilhados em [`shared/schemas/schemas_scraper.py`](../shared/schemas/schemas_scraper.py).
- Autenticação opcional entre serviços é configurada pelas variáveis `SCRAPER_SERVICE_AUTH_HEADER` e `SCRAPER_SERVICE_AUTH_TOKEN`.
- O cliente interpreta `ParseResponse` completo, respeitando cenários `no_result`, `304 Not Modified`, erros de validação e `unsupported_by_robots`.
- Lógicas de parsing permanecem exclusivas do `market_scraper`; ao evoluir o contrato, atualize primeiro o diretório `shared/` e reaproveite validações existentes.

## Testes
Execute os testes específicos com:
```bash
pytest market_alert -q
```
Fixtures cobrem tarefas Celery, integrações com o scraper e camadas de persistência.
