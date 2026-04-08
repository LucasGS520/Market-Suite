# Shared — Infraestrutura e Contratos Compartilhados

Biblioteca interna sem servidor próprio. Importada por todos os serviços
(`market_alert`, `market_orchestrator`, `market_scraper`) como dependência de
pacote. Como regra, nenhum módulo daqui importa de qualquer serviço específico;
a única exceção documentada é `shared/clients/scraper/scraper_client.py`.

---

## Estrutura

```
shared/
├── clients/                    # Clientes de serviços externos
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
│   ├── shared_schemas_orchestrator.py  # DTOs de orquestração (canônico) — versão 1
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
└── __init__.py
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

---

## Clientes de Integração entre Serviços

Os clientes em `shared/clients` padronizam a comunicação entre módulos e evitam duplicação de lógica de transporte (HTTP, Temporal, enqueue de tasks). A ideia é centralizar configuração, contratos e tratamento básico de erros no ponto canônico.

### `shared/clients/celery/task_dispatcher.py`

Cliente responsável por **disparar tarefas assíncronas no Celery** de forma padronizada.

- **Objetivo:** encapsular `send_task/apply_async`, filas, roteamento e metadados comuns.
- **Responsabilidades principais:**
   - enviar payloads já serializáveis;
   - aplicar configuração de fila/prioridade/retry conforme convenção do projeto;
   - devolver identificadores de task para rastreabilidade.
- **Por que centralizar:** evita que cada serviço implemente seu próprio envio de task com variações de nome de fila, headers e política de retry.
- **Boas práticas de uso:**
   - enviar somente dados de contrato (DTOs de `shared.schemas`);
   - registrar correlation/trace id quando disponível;
   - manter idempotência no consumidor, não no dispatcher.

### `shared/clients/scraper/scraper_client.py`

Cliente canônico para **consumo da capacidade de scraping** usada pelo ecossistema.

- **Objetivo:** oferecer interface única para solicitar coleta/extração de dados de produto.
- **Responsabilidades principais:**
   - montar requisições para o serviço/componente de scraping;
   - normalizar respostas para contratos compartilhados;
   - tratar falhas de integração (timeout, indisponibilidade, resposta inválida).
- **Exceção arquitetural documentada:** este cliente pode ter acoplamento específico já registrado na arquitetura do projeto.
- **Boas práticas de uso:**
   - validar entrada antes de chamar scraping;
   - aplicar timeout explícito e fallback seguro;
   - nunca embutir regra de negócio de `market_alert` no cliente.

### `shared/clients/temporal/orchestrator_client.py`

Cliente oficial para **interação com Temporal** (workflows de orquestração).

- **Objetivo:** centralizar criação/configuração do client Temporal e operações de workflow.
- **Responsabilidades principais:**
   - iniciar workflows com `workflow_id` e `task_queue` padronizados;
   - enviar sinais/queries para workflows em execução;
   - encapsular detalhes de conexão, namespace e políticas de retry.
- **Por que é canônico:** impede múltiplas implementações locais de acesso ao Temporal e reduz drift entre serviços.
- **Boas práticas de uso:**
   - usar sempre contratos de `shared.schemas.shared_schemas_orchestrator`;
   - manter nomes de workflow/signal/query versionados e estáveis;
   - registrar contexto de observabilidade (trace/correlation id) nas chamadas.

### Diretriz Geral para os três clientes

- São pontos de **integração técnica**, não de regra de negócio.
- Devem expor APIs pequenas e previsíveis, orientadas a contrato.
- Mudanças de transporte/protocolo devem ocorrer aqui, preservando os chamadores.

---

## Regras de Uso

1. **Sem imports de serviços específicos.** `shared` não importa de
   `market_alert`, `market_orchestrator` ou `market_scraper`.
2. **Sem lógica de domínio.** Apenas infraestrutura, contratos e utilitários
   sem estado.
3. **Tipos de orquestração sempre via `shared.schemas.shared_schemas_orchestrator`.**
   Nunca recriar `CollectionPayload` ou `DispatchActivityOutput` em outro módulo.
4. **Cliente Temporal sempre via `shared.clients.temporal.orchestrator_client`.**
   Os caminhos legados foram removidos; não reintroduzir shims locais.

---

## Fronteiras de Domínio

### Matriz de Responsabilidade

| Módulo | Pode depender de | NÃO pode depender de |
|--------|-----------------|----------------------|
| `shared` | bibliotecas externas (SQLAlchemy, Redis, Pydantic, structlog) | `market_orchestrator`; `market_scraper`; `market_alert` (exceto algumas exceções quando documentadas) |
| `market_alert` | `shared` | — (via `shared` acessa Temporal, Redis, DB) |
| `market_orchestrator` | `shared` | `market_alert`; `market_scraper` |
| `market_scraper` | `shared` (schemas neutros) | `market_alert`; `market_orchestrator` |

### Regras Obrigatórias

- **`shared` não importa serviços específicos como regra geral**.
- **`shared/clients/scraper/scraper_client.py` importa `market_alert`** — exceção arquitetural consciente, isolada no cliente canônico de scraping.
- **Contratos de orquestração** ficam em `shared/schemas/shared_schemas_orchestrator.py` como dataclasses/Pydantic puros sem I/O.
- **Utilitários** só entram em `shared` se forem verdadeiramente neutros (sem regra de negócio de nenhum domínio).
---

## Testes do Modulo

Executar os comandos a partir de `backend/` para garantir uso do
`backend/pytest.ini`, coleta explicita de `shared/tests` e auto-marcacao por
pasta (`unit` e `integration`).

### Execucao local padrao

Suite unitaria do `shared`:

```powershell
..\.venv\Scripts\python.exe -m pytest shared/tests/unit -q
```

Suite de integracao controlada do `shared`:

```powershell
..\.venv\Scripts\python.exe -m pytest shared/tests/integration -q
```

Suite completa do `shared`:

```powershell
..\.venv\Scripts\python.exe -m pytest shared/tests -q
```

### Selecao por marker para pipeline

Etapa rapida padrao (`unit`):

```powershell
..\.venv\Scripts\python.exe -m pytest shared/tests -m unit -q
```

Etapa posterior de integracao controlada (`integration`):

```powershell
..\.venv\Scripts\python.exe -m pytest shared/tests -m integration -q
```

Governanca esperada para pipeline:

- `unit` como estagio padrao e rapido;
- `integration` em estagio posterior;
- nenhum cenario unitario depende de Redis, Temporal, HTTP ou banco reais.

### Cobertura inicial do `shared`

Meta inicial: **80% de cobertura de linhas do pacote `shared`**, priorizando:

- contratos em `schemas`;
- utilitarios criticos em `utils`;
- infra de baixo nivel em `infra`;
- clientes canonicos em `clients`.

Comando canonico de cobertura:

```powershell
..\.venv\Scripts\python.exe -m pytest shared/tests --cov=shared --cov-report=term-missing --cov-fail-under=80 -q
```

O comando de cobertura requer `pytest-cov` instalado no ambiente de testes.
Ele nao foi colocado em `addopts` global para evitar quebrar ambientes que
ainda nao possuam o plugin.
