# Plano de Refatoração — Tarefas Celery no `market_alert`

## Análise de Riscos e Decisões Chave

### Decisão Técnica Principal
**Consolidar Service Layer existente**: O projeto já possui serviços dedicados (`services_scraper_monitored`, `services_scraper_competitor`, `services_comparison`, `services_notifications`) que encapsulam lógica de orquestração, decisões de negócio e coordenação entre CRUD/domain/infra. O objetivo é **padronizar e consolidar esses services**, removendo fragmentos de lógica que ainda residem nas tasks, e garantir que as tasks Celery sejam apenas cascas finas que delegam para esses services.

**Decisões adotadas:**
- **Reutilizar services existentes** → `services_scraper_*`, `services_comparison`, `services_notifications` já implementam a maioria das responsabilidades
- **Consolidar APIs** → padronizar contrato de cada service (entrada/saída, tratamento de erros, trace ID)
- **Mover fragmentos de tasks para CRUD** → operações como `_activate_pending_monitored`, `_fetch_recent_prices`, `_mark_invalid_product` saem das tasks e viram funções CRUD idempotentes
- **Centralizar locks** → gestão de lock Redis concentrada em um único ponto (service ou orchestrator), não espalhada em múltiplas tasks

### Riscos Principais
**1. Quebra de compatibilidade com código legado que chama tasks ou services diretamente**
- Mitigação: Manter **aliases de compatibilidade** e **wrappers deprecados** por 1-2 sprints; adicionar warnings de log

**2. Fragmentação de responsabilidades entre tasks atuais e services**
- Ex.: `_activate_pending_monitored`, `_fetch_recent_prices` ainda residem em tasks e precisam migrar para CRUD
- Mitigação: Fase 1 executa antes de Fase 2, extraindo todas as operações de persistência para CRUD de forma isolada

**3. Coleta contínua (`continuous_collector_task`) é crítica**
- Parada não intencional pode desativar monitoramento 24/7 de centenas de produtos
- Mitigação: Testar extensa em staging; implementar circuit breaker e health checks; usar feature flags para rollout gradual

### Dependências
- **Redis disponível**: Locks de coleta, dedup de notificações, cooldown e circuit breakers dependem de Redis funcional
- **Banco de dados**: Novas queries CRUD precisam de índices otimizados (ex.: `monitored.status`, `notification.status`); verificar execution plans
- **Celery workers rodando**: Payloads legados (dict) e novos (Pydantic) coexistirão durante transição; manter serializer compatível
- **Monitoring/APM**: Trace ID já está em `CollectionPayload` e logs; integração com OpenTelemetry é opcional (Fase 4)
- **Services estáveis**: `services_scraper_*`, `services_comparison`, `services_notifications` são ponto de apoio — qualquer mudança neles quebra tasks

---

## Plano de Implementação (Checklist)

### Fase 1: Extração de Persistência
**Objetivo:** Eliminar fragmentos de lógica de persistência que ainda residem nas tasks, consolidando-os em operações CRUD idempotentes e reutilizáveis. Remover helpers privados das tasks para CRUD.

#### 1.1 Criar Operações CRUD que Faltam
- [ ] **CRUD Monitored**: Criar `crud_monitored.activate_pending_monitored(db, monitored_id, commit=True)` para substituir `_activate_pending_monitored()` de `collector_product_task.py`
  - Retorna o monitorado atualizado ou None
  - Idempotente: sem efeito se já estiver `active`
- [ ] **CRUD Monitored**: Criar `crud_monitored.mark_monitored_as_invalid(db, monitored_id, reason, attempts, touched_at=None)` para substituir branch monitorado de `_mark_invalid_product()`
  - Similar à função `mark_monitored_product_failed` que já existe; consolidar se necessário
- [ ] **CRUD Competitor**: Criar `crud_competitor.mark_competitor_as_invalid(db, competitor_id, reason, attempts, touched_at=None)` para substituir branch concorrente de `_mark_invalid_product()`
  - Pausar concorrente ou marcar como failed; documentar política
- [ ] **CRUD Price History**: Criar `crud_price_history.fetch_recent_prices(db, monitored_id, limit=2)` para substituir `_fetch_recent_prices()` em `compare_prices_task.py`
  - Retorna tupla `(price_previous, price_current)` ou `(None, None)`

#### 1.2 Substituir Chamadas em Tasks
- [ ] **collector_product_task.py**: Substituir `_activate_pending_monitored()` por `crud_monitored.activate_pending_monitored()`
- [ ] **collector_product_task.py**: Substituir `_mark_invalid_product()` por chamadas ao CRUD de monitored ou competitor
  - Remover lógica de branch (monitored vs. competitor) da task; mover para service se necessário
- [ ] **compare_prices_task.py**: Substituir `_fetch_recent_prices()` por `crud_price_history.fetch_recent_prices()`
- [ ] **compare_prices_task.py**: Remover query duplicada de monitorado + user; usar serviço existente ou consolidar em CRUD

#### 1.3 Validação e Limpeza
- [ ] **Deletar Funções Privadas**: Remover `_activate_pending_monitored()`, `_mark_invalid_product()`, `_fetch_recent_prices()` das tasks
- [ ] **Verificar Imports**: Garantir que nenhuma task importa `SessionLocal` diretamente (exceto no ponto de entrada da task)

---

### Fase 2: Consolidação de Services Orquestradores
**Objetivo:** Padronizar e consolidar a API dos services existentes, garantindo contrato claro entre task → service → CRUD. Reutilizar `services_scraper_*`, `services_comparison`, `services_notifications` como ponto de orquestração único.

#### 2.1 Consolidar Service de Coleta (`services_scraper_*`)
**Status Atual:** Services existem (`services_scraper_monitored.py`, `services_scraper_competitor.py`) + orchestrator (`collector_service_orchestrator.py`)
- [ ] **services_scraper_monitored.py**: Documentar contrato de `scrape_monitored_product(db, url, user_id, payload, *, collected_at=None) -> ScrapeResult`
  - Valida pré-condições (produto pausado?)
  - Executa scraping via `ScraperClient`
  - Persiste via CRUD (`create_or_update_monitored_product_scraped`)
  - Retorna `ScrapeResult` padronizado
- [ ] **services_scraper_competitor.py**: Documentar contrato análogo para concorrentes
- [ ] **collector_service_orchestrator.py**: Consolidar como **único ponto de enfileiramento**
  - `enqueue_collect(payload, countdown=None)` → entrada única para Celery
  - `build_monitored_payload()`, `build_competitor_payload()` → builders tipados
  - Documentar que tasks **não devem** chamar `apply_async` diretamente

#### 2.2 Consolidar Service de Comparação (`services_comparison`)
**Status Atual:** Service existe (`services_comparison.py`) com `run_price_comparison()`
- [ ] **services_comparison.py**: Garantir que `run_price_comparison(db, monitored_id, tolerance=None)` é a entrada única
  - Valida pré-condições (produto inativo?)
  - Carrega monitorado + concorrentes
  - Calcula comparação via `services_comparison_calculator`
  - Persiste resultados
  - Retorna dict com `summary`, `comparison_id`, etc.
- [ ] **compare_prices_task.py**: Remover lógica de decisão de notificação
  - Task apenas chama `services_comparison.run_price_comparison()` + delega notificações para `evaluate_and_create_notifications()`
  - Remover `_fetch_recent_prices()` via Fase 1

#### 2.3 Consolidar Service de Notificações (`services_notifications`)
**Status Atual:** Service existe (`notifications/services_notifications.py`) com `evaluate_and_create_notifications()` e `process_notification()`
- [ ] **services_notifications.py**: Documentar dois pontos de entrada:
  1. `evaluate_and_create_notifications()` → recebe monitorado + snapshots + preferências → retorna lista de IDs criados
  2. `process_notification()` → recebe ID → executa envio + registra tentativa
- [ ] **notifications_enqueue_task.py**: Mover enfileiramento para serviço
  - Criar método `services_notifications.enqueue_pending_notifications(notification_ids=None, limit=200, trace_id=None) -> int`
  - Encapsula `get_pending_notifications()` + enfileiramento individual de `send_notification_task`
  - Padroniza headers/trace_id em todos os envios

#### 2.4 Criar/Consolidar Service de Verificação (Email/SMS)
- [ ] **services/verification_service.py** (novo ou consolidar `services_users.py`): Ponto único para verificação de email/SMS
  - Métodos: `send_email_verification(db, user_id, token)`, `send_phone_otp(db, user_id, otp)`
  - Valida usuário, construir mensagem, chamar adapter, persistir tentativa
  - Define retry policy centralizada

#### 2.5 Validação de Services Consolidados
- [ ] **Teste de Contrato**: Verificar que cada serviço tem assinatura clara (entrada/retorno/exceções)
- [ ] **Documentação**: Atualizar docstrings; criar diagrama de dependências

---

### Fase 3: Refatoração de Tasks para Cascas Finas
**Objetivo:** Transformar cada task em um wrapper mínimo que apenas chama service consolidado e trata exceções Celery. Centralizar gestão de locks de coleta em um único ponto (service ou orchestrator).

#### 3.1 Refatorar collector_product_task
- [ ] **collector_product_task.py**: Simplificar `collect_product()` para apenas:
  1. Validar payload básico contra `CollectionPayload` schema
  2. Chamar `services_scraper_monitored.scrape_monitored_product()` ou `services_scraper_competitor.scrape_competitor_product()`
  3. Tratar resultado+erros, registrar desfecho
  4. Deletar helpers privados: `_activate_pending_monitored()`, `_mark_invalid_product()`, `_collect_monitored()`, `_collect_competitor()` — usar CRUD + services
- [ ] **Lock Redis**: Mover gerenciamento para este pontoÍtnico
  - Adquirir antes de chamar service
  - Liberar no finally
  - Documente que é o único lugar de lock para coleta (evitar duplicação)
- [ ] **Session DB**: Abrir uma única sessão, passar para service
- [ ] **Celery Retry**: Manter `self.retry()` para `lock_skipped`; remover outros retries (service trata)

#### 3.2 Refatorar compare_prices_task
- [ ] **compare_prices_task.py**: Reduzir para apenas:
  1. Chamar `services_comparison.run_price_comparison(db, monitored_id)`
  2. Chamar `services_notifications.evaluate_and_create_notifications()` com snapshots
  3. Enfileirar notificações via `services_notifications.enqueue_pending_notifications()`
  4. Deletar `_fetch_recent_prices()` — usar `crud_price_history.fetch_recent_prices()` via Fase 1
- [ ] **Múltiplas sessões DB**: Consolidar em uma única sessão se possível (comparision + notificaction compartilham contexto)
- [ ] **Validações de pre-condição**: Mover para `services_comparison` (pausado?, inativo?)

#### 3.3 Refatorar continuous_collector_task
- [ ] **continuous_collector_task.py**: Manter loop `while True:` mas delegar cada coleta para services existentes
  - Loop continua gerenciando Redis polling + abuse detection
  - Para cada batch: chamar `services_scraper_monitored|competitor` **ou** chamar `collector_product_task` via `apply_async` (menos duplicação)
- [ ] **Lock continuó**: Centralizar em `ContinuousCollectorManager` (novo service dedicado ou manter no orchestrator?)
  - Adquirir lock de atividade antes de entrar no loop
  - Renovar periodicamente
  - Liberar ao sair
  - Prevenir múltiplas instâncias rodam simultanéamente

#### 3.4 Refatorar notifications_enqueue_task e send_notification_task
- [ ] **notifications_enqueue_task.py**: Delegar para `services_notifications.enqueue_pending_notifications(notification_ids=None, limit=200, trace_id=None)`
  - Remove duplicação de `get_pending_notifications()` + enfileiramento
  - Padroniza trace_id + headers
- [ ] **send_notification_task.py**: Delegar para `services_notifications.process_notification(db, notification_id)`
  - Task já é uma casca fina; manter assim

#### 3.5 Refatorar verification_tasks
- [ ] **verification_tasks.py**: Reduzir `send_email_verification()` e `send_phone_otp()` para chamar `services_verification.send_email_verification()` e `services_verification.send_phone_otp()`
- [ ] **Retry policy**: Centralizada no service (não na task)
- [ ] **Validações**: Mover para service

---

### Fase 4: Padronização de Retry e Observabilidade
**Objetivo:** Consolidar retry policies, padronizar trace ID propagado e implementar dead letter queue para falhas permanentes.

#### 4.1 Consolidar Política de Retry Centralizada
**Status Atual:** `RetryPolicy` existe em `orchestrator/retry_policy.py` com lógica de backoff
- [ ] **core/retry_policies.py**: Centralizar todas as políticas nomeadas (`COLLECTION_RETRY`, `NOTIFICATION_RETRY`, `VERIFICATION_RETRY`) herdando de `RetryPolicy`
  - Define `max_retries`, `retry_backoff`, `exclude_from_retry`, `autoretry_for` para cada domínio
- [ ] **Aplicar nas tasks**: Usar `@celery_app.task(..., **COLLECTION_RETRY.celery_kwargs)` em vez de configurações inline
- [ ] **Documentação**: Criar tabela em `tasks/README.md` mapeando task → política de retry

#### 4.2 Consolidar Trace ID Propagado
**Status Atual:** `trace_id` já está em `CollectionPayload` e logs estão estruturados
- [ ] **Utilizar contextvars**: Criar `shared/utils/trace_context.py` para gerenciar trace_id do contexto de execução (thread-local)
  - `get_or_create_trace_id()` → retorna ID do contexto ou gera novo
  - `set_trace_id(trace_id)` → injeta no contexto
- [ ] **Services**: Aceitar `trace_id` opcional; propagar via `trace_context.set_trace_id()` para chamadas aninhadas
- [ ] **Tasks**: Chamar `trace_context.set_trace_id(trace_id or self.request.id)` no início
- [ ] **Celery Headers**: Configurar para propagar via `x-trace-id` header (opcional; depende de serializer)
- [ ] **Logging**: Modificar logger bound para sempre incluir `trace_id` do contexto nos estruturados

#### 4.3 Implementar Dead Letter Queue
- [ ] **core/celery_schedule.py**: Criar fila `dead_letter` com exchange dedicado
- [ ] **tasks/**: Configurar `on_failure` callback em tasks críticas (`collector_product_task`, `compare_prices_task`, `send_notification_task`) para enviar para DLQ após `max_retries`
- [ ] **tasks/dlq_handler.py**: Criar task dedicada que consome DLQ, registra em tabela de auditoria e notifica operadores
- [ ] **models/models_task_failures.py**: Criar model `TaskFailure` para persistir falhas permanentes (task_name, payload, exception, trace_id, retry_count, created_at)
- [ ] **CRUD**: Criar `crud_task_failures.py` para query/alerta de falhas

---

### Fase 5: Separação de Configuração e Operação
**Objetivo:** Consolidar ponto único de enfileiramento e separar lógica operacional de `celery_app.py`.

#### 5.1 Consolidar Ponto Único de Enfileiramento
**Status Atual:** `collector_service_orchestrator.py` já possui `enqueue_collect()`
- [ ] **collector_service_orchestrator.py**: Manter como único ponto de enfileiramento para coleta
  - `enqueue_collect(payload, countdown=None)` aceita `CollectionPayload` ou dict (compat)
  - `enqueue_monitored_collection()`, `enqueue_competitor_collection()` são wrappers com builders
  - `enqueue_competitors_for_monitored()` enfileira batch de concorrentes com agravo de delay
  - Documentar que nenhuma rota/service deve chamar `apply_async()` diretamente
- [ ] **Criar `services/task_enqueuer.py`** (opcional): se quiser consolidar **todos** os enfileiramentos (coleta + comparacao + notificacao) em uma classe única
  - `TaskEnqueuer.enqueue_collection(payload, trace_id=None, priority=5) -> str`
  - `TaskEnqueuer.enqueue_comparison(monitored_id, trace_id=None) -> str`
  - `TaskEnqueuer.enqueue_notification(notification_id, trace_id=None) -> str`
  - Método interno `_apply_async_with_trace_id()` que padroniza headers
- [ ] **routes/**: Auditar que estão usando orchestrator ou task_enqueuer (não `apply_async` direto)

#### 5.2 Extrair Lógica Operacional de celery_app.py
**Status Atual:** `celery_app.py` contient configuração + hooks operacionais
- [ ] **core/task_loader.py** (novo): Mover `_force_import_task_modules()` — carrega dinamicamente todas as tasks
- [ ] **services/continuous_collector_manager.py** (novo): Mover lógica de autostart/lock da coleta contínua
  - `ContinuousCollectorManager.autostart_if_enabled()` — é chamado pelo `@worker_ready.connect`
  - Métodos internos para gerenciar lock, polling, abort signal
- [ ] **celery_app.py**: Reduzir para apenas configuração pura
  - Exchanges, queues, serialization, timezone
  - Hooks (`worker_ready`) como calls simples para managers

#### 5.3 Refatorar Rotas para Usar Wrapper
- [ ] **routes/routes_monitored.py**: Auditar e substituir chamadas diretas de `apply_async()` por `TaskEnqueuer.enqueue_collection()` ou `enqueue_monitored_collection()`
- [ ] **routes/routes_competitors.py**: Idem
- [ ] **routes/routes_dashboard.py**: Idem para qualquer enfileiramento dinâmico

#### 5.4 Validação de Configuração e Wrappers
- [ ] **Auditoria Celery**: Validar que não há `apply_async` disperso nas rotas/services

---

### Fase 6: Limpeza e Documentação Final
**Objetivo:** Remover código legado que se tornou obsoleto após consolidação das fases anteriores, atualizar documentação e validar arquitetura final.

#### 6.1 Remover Código Legado
- [ ] **tasks/**: Deletar funções privadas que migraram para CRUD durante as fases anteriores
  - `_activate_pending_monitored()` de `collector_product_task.py`
  - `_mark_invalid_product()` de `collector_product_task.py`
  - `_fetch_recent_prices()` de `compare_prices_task.py`
  - `_collect_monitored()`, `_collect_competitor()` se duplicarem em services
- [ ] **utils/**: Avaliar e consolidar ou remover conforme migração das fases:
  - `price_comparator.py`: Mover `schedule_comparison_after_commit()` para `services_comparison`; deletar se vazio
  - `collector_result.py`: Consolidar helpers em service ou remover se não-usado
  - `continuous_dispatch.py`: Mover para `services/continuous_collector_manager.py`
  - `rate_limiter.py`: Manter se genérico; mover helpers domínio-específicos
- [ ] **tasks/scraper_tasks.py**: Deletar se era apenas wrapper de compatibilidade

#### 6.2 Validação Arquitetural Final
- [ ] **Auditoria de Imports**: Verificar que tasks **não** importam CRUD/domain diretamente (apenas services)
- [ ] **Auditoria de Session Management**: Verificar que cada task abre **apenas uma** sessão DB (dentro do service ou task)
- [ ] **Auditoria de Retry Policies**: Verificar que todas as tasks têm policy nomeada documentada

---

## 4. Definição de Pronto (Definition of Done)

### Funcionalidade
- [ ] Todas as tasks existem como cascas finas (<50 linhas, apenas delegação)
- [ ] Toda lógica de negócio está em services testáveis isoladamente
- [ ] Toda persistência está em CRUD, sem queries diretas em tasks/services
- [ ] Retry policies estão padronizadas e documentadas
- [ ] Trace ID é propagado através de todo o fluxo (API → Task → Service → CRUD)
- [ ] Dead Letter Queue captura falhas permanentes

### Qualidade
- [ ] Nenhuma importação circular detectada pelo linter
- [ ] Nenhuma função privada de DB dentro de tasks
- [ ] Session DB aberta apenas uma vez por task execution

### Documentação
- [ ] README.md atualizado com arquitetura refatorada
- [ ] Diagrama de fluxo disponível mostrando camadas (API → Enqueuer → Task → Service → CRUD)
- [ ] Guia de migração documentando breaking changes
- [ ] Políticas de retry documentadas em tabela

---

## Observações Finais

### Ordem de Execução Recomendada
Execute as fases **sequencialmente** (não em paralelo). Cada fase deve ser finalizada antes de iniciar a próxima.

### Riscos de Regressão
- **Coleta contínua** (`continuous_collector_task`) é crítica — qualquer bug pode parar monitoramento 24/7. Teste extensivamente em staging antes de produção.
- **Trace ID propagation** pode quebrar se Celery serializer não preservar headers customizados — validar cedo na Fase 4.
