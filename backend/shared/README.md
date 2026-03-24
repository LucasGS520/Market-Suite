# shared — Infraestrutura e Contratos Compartilhados

Biblioteca interna sem servidor próprio. Importada por todos os serviços
(`market_alert`, `market_orchestrator`, `market_scraper`) como dependência de
pacote. Nenhum módulo daqui importa de qualquer serviço específico.

---

## Estrutura

```
shared/
├── clients/                    # Clientes de serviços externos
│   └── orchestrator_client.py  # TemporalOrchestrationClient (canônico)
├── core/
│   └── config_base.py          # ConfigBase — BaseSettings compartilhada
├── enums/                      # Enums e constantes globais
│   ├── cache_keys.py
│   ├── redis_key_patterns.py
│   ├── redis_streams.py
│   └── block_results.py
├── infra/                      # Infraestrutura de baixo nível
│   ├── db/
│   │   ├── base.py             # DeclarativeBase SQLAlchemy
│   │   └── database.py         # SessionLocal, engine
│   ├── redis/
│   │   ├── idempotency.py      # IdempotencyStore
│   │   └── streams.py          # RedisStreams
│   ├── cache_strategy.py       # CacheStrategy
│   ├── logging.py              # configure_structlog() — factory de logging
│   ├── rate_limiter.py         # Protocol RateLimiter + RedisRateLimiter
│   └── redis_pubsub.py         # RedisPubSub
├── schemas/                    # Contratos de dados compartilhados
│   ├── shared_schemas_orchestrator.py  # DTOs de orquestração (canônico)
│   ├── shared_schemas_products.py
│   └── shared_schemas_scraper.py
├── scheduling/                 # Agendamento periódico
│   ├── context.py
│   └── scheduler.py
├── utils/                      # Utilitários sem estado
│   ├── http_headers.py
│   ├── redis_client.py
│   ├── redis_locks.py
│   ├── text_sanitization.py
│   ├── trace_context.py
│   └── url_validation.py
├── exceptions.py               # Exceções base compartilhadas
└── orchestrator_contracts.py   # Factory methods para DTOs de orquestração
```

---

## Contratos de Orquestração

### Por que existem aqui

`market_orchestrator` e `market_alert` precisam trocar dados durante o ciclo de
vida de uma coleta. Antes da refatoração, esses tipos estavam em
`market_alert`, criando uma dependência direta do orquestrador no serviço de
domínio — um acoplamento proibido. Os contratos foram movidos para `shared`
para que ambos os serviços importem do mesmo ponto neutro.

### `shared/schemas/shared_schemas_orchestrator.py`

Tipos canônicos usados pela cadeia `API → Temporal → Activity → Celery`:

| Tipo | Descrição |
|------|-----------|
| `CollectionPayload` | Payload enviado ao Celery para iniciar uma coleta |
| `validate_payload` | Valida e deserializa `CollectionPayload` a partir de dict |
| `DispatchActivityOutput` | Retorno da activity `dispatch_collection` |
| `QueryStatusOutput` | Retorno da activity `query_collection_status` |
| `PolicyActivityOutput` | Retorno da activity `fetch_monitored_policy` |
| `WorkflowStateSnapshot` | Snapshot de estado do workflow para persistência |
| `CollectionResult` | Resultado final de uma coleta processada |

**Regra:** nenhum desses tipos importa de `market_alert`, `market_orchestrator`
ou qualquer infraestrutura. São dataclasses/Pydantic puros.

### `shared/orchestrator_contracts.py`

Factory methods para construir os DTOs de forma padronizada:

```python
from shared.orchestrator_contracts import (
    create_collection_payload,
    build_activity_result,
    build_dispatch_output,
)
```

### `shared/clients/orchestrator_client.py`

Cliente Temporal de alto nível. Ponto canônico de interação com o workflow
`MonitoredProductWorkflow`:

```python
from shared.clients.orchestrator_client import TemporalOrchestrationClient, get_temporal_client

# Singleton assíncrono (para uso em contexto async/FastAPI)
client = await get_temporal_client()

# Fachada síncrona (para uso em workers Celery)
orchestrator = TemporalOrchestrationClient()
orchestrator.signal_with_start_sync(workflow_input)
orchestrator.pause_sync(monitored_id)
orchestrator.resume_sync(monitored_id, immediate_collect=True)
orchestrator.query_sync(monitored_id)          # → WorkflowSnapshot | None
orchestrator.notify_competitor_changed_sync(monitored_id, competitor_id)
```

**Compatibilidade retroativa:** `market_orchestrator/alert/alert_client.py` e
(se presente) `market_alert/orchestrator/alert_client.py` são re-exportadores
que apontam para este módulo.

---

## Infraestrutura

### `shared/infra/logging.py`

```python
from shared.infra.logging import configure_structlog

configure_structlog(log_level="INFO", log_format="json")
```

Configura structlog para JSON em produção e console em desenvolvimento.
Chamado no startup de cada serviço via `logging_config.py` local.

### `shared/infra/rate_limiter.py`

```python
from shared.infra.rate_limiter import RedisRateLimiter

limiter = RedisRateLimiter(redis_client, key="scraper", max_calls=10, window=60)
allowed = await limiter.is_allowed()
```

### `shared/infra/db/database.py`

```python
from shared.infra.db.database import SessionLocal

db = SessionLocal()
try:
    result = db.execute(text("SELECT ..."))
finally:
    db.close()
```

### `shared/core/config_base.py`

`ConfigBase` herda de `pydantic_settings.BaseSettings`. Lê variáveis de
ambiente + arquivo `.env.<SERVICE_NAME>` determinado pela variável de ambiente
`SERVICE_NAME`. Cada serviço define sua própria classe de configuração
herdando de `ConfigBase`.

---

## Regras de Uso

1. **Sem imports de serviços específicos.** `shared` não importa de
   `market_alert`, `market_orchestrator` ou `market_scraper`.
2. **Sem lógica de domínio.** Apenas infraestrutura, contratos e utilitários
   sem estado.
3. **Tipos de orquestração sempre via `shared.schemas.shared_schemas_orchestrator`.**
   Nunca recriar `CollectionPayload` ou `DispatchActivityOutput` em outro módulo.
4. **Cliente Temporal sempre via `shared.clients.orchestrator_client`.**
   Os re-exportadores locais existem apenas para retrocompatibilidade de imports
   já consolidados.
