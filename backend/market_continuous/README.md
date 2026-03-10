# market_continuous — Loop Contínuo de Coleta

Processo standalone responsável pelo ciclo de vida do coletor contínuo de preços.
Extraído do runtime Celery para permitir evolução independente, deploy dedicado
e futura reimplementação em linguagem compilada (Go/Rust) se desejado.

## Visão geral

O pacote `market_continuous` contém a implementação do loop que consome a fila
de prioridade em Redis, despacha tarefas de scraping via Celery e aplica
políticas de reenqueue/recover para manter a consistência DB ↔ Redis.

Esta versão foi modularizada para refletir responsabilidades claras:

```
market_continuous/
├─ __init__.py
├─ README.md
├─ main.py                 # Entrypoint standalone
├─ orchestrator/           # Loop e lógica de despacho
│  ├─ __init__.py
│  ├─ manager.py           # Ciclo de vida, lock, autostart, loop principal
│  ├─ dispatcher.py        # Despacho de tasks e decisões de reenqueue
│  ├─ callbacks.py         # Callbacks padrão pós-coleta (success/error)
│  └─ reconciliation.py    # Reconciliação DB -> fila Redis
├─ queue/                  # Abstrações de domínio para fila
│  ├─ __init__.py
│  └─ collection_queue.py  # `CollectionQueue` (API orientada ao domínio)
└─ services/               # Implementações e primitives
	 ├─ __init__.py
	 └─ services_priority_queue.py  # `PriorityQueueService` (Redis sorted-set)
```

## Responsabilidades por componente

- **`orchestrator.manager`**: garante instância única via lock Redis,
	executa o loop de consumo, aguarda resultados (`AsyncResult.get()`)
	e chama callbacks inline.
- **`orchestrator.dispatcher`**: constrói payloads, despacha tasks via
	`CollectionEnqueuer` e decide se o monitorado deve ser reenfileirado.
- **`orchestrator.callbacks`**: funções utilitárias de logging para
	sucesso/erro de coletas (o reenqueue é tratado pelo `manager`).
- **`orchestrator.reconciliation`**: reconcilia monitorados ativos do
	PostgreSQL com a fila de prioridade, corrigindo perdas após restarts.
- **`queue.collection_queue`**: camada de domínio que expõe operações
	de enqueue/pop/reclaim/mark-as-done sem expor detalhes do Redis.
- **`services.services_priority_queue`**: implementação baseada em
	Redis Sorted Sets e scripts atômicos para `pop_due` e reclaim.

## Chaves Redis e prefixos usados

- `lock:continuous_collector` — singleton lock para o processo do loop
- `collection:priority_queue:<env>` — Sorted Set principal (score = next_check_at)
- `collection:processing:<env>` — Sorted Set de itens em processamento
- `market_alert:collection:reconciliation:running` — flag TTL para reconciliação
- `market_alert:continuous_collector:autostart` — lock curto de autostart
- `market_alert:continuous_collector:autostart:cooldown` — cooldown pós-falha

> Observação: os nomes exatos das chaves podem ser parametrizados via
> `settings` no `market_alert.core.config_alert`.

## Como executar (standalone)

No ambiente de desenvolvimento com as dependências carregadas:

```bash
cd backend
python -m market_continuous.main
```

O processo:
- faz uma reconciliação inicial da fila contra o banco (reconciliation)
- entra no loop de consumo e processa lotes definidos por
	`CONTINUOUS_WORKER_BATCH_SIZE`
- aguarda resultados de coleta via Celery e aplica o fluxo de reenqueue

## Integração com o restante do sistema

- `CollectionQueue` é consumido por serviços de lifecycle em `market_alert`
	(ex.: `products/services/services_monitored_lifecycle.py`) — os imports
	passaram a apontar para `market_continuous.queue.collection_queue`.
- O despachador usa `market_alert.infraestructure.celery.enqueuer.CollectionEnqueuer`
	para enviar payloads para as tasks de scraping.

## Roadmap e próximos passos

- Manter o loop em Python com menor superfície e testes de integração
	(Redis + Celery) antes de considerar reescrita.
- Possibilidade de extrair o loop para um serviço leve em Go/Rust para
	reduzir latência por item e uso de memória.
- Adicionar métricas e alertas específicos (latência por item, reclaim rate,
	taxa de enfileiramento/derrubada) e testes de falha com Redis real.

## Operação e observabilidade

- Logs estruturados com `trace_id` para correlação entre dispatch → task → callback.
- Recomenda-se monitorar: tamanho da fila, itens prontos (ready_count),
	tempo médio de processamento e reclaim frequency.

---

Mantive o formato e nível de detalhe alinhado ao `market_scraper/README.md`.
Se quiser, eu adapto para incluir exemplos de `systemd`/Docker Compose
ou snippets de `docker-compose.yml` para execução em container.
