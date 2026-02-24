
# Plano de Refatoração — Responsabilidade de Notificações

## Análise de Riscos e Decisões Chave

### Decisão Técnica Principal
**Introduzir uma Service Layer (`services_notifications.py`) como ponto único de orquestração** que:
- Chama o `evaluator` para gerar candidatos
- Transforma candidatos em notificações persistidas via CRUD
- Aplica locks, dedup e cooldown de forma isolada
- Enfileira para entrega (via Celery ou outro mecanismo)

Isso resolve a ausência de service layer e centraliza responsabilidades atualmente dispersas.

### Risco Principal
**Quebrar o fluxo existente de notificações durante a refatoração**, causando perda de alertas críticos em produção.

**Mitigação:**
- Refatoração incremental com testes a cada fase
- Manter compatibilidade retroativa durante a transição
- Usar feature flags para habilitar novo fluxo gradualmente
- Validar que tasks Celery existentes (se houver) continuam funcionando
- Manter logs detalhados para rastrear comportamento antes/depois

### Dependências Externas
- **Redis**: Precisa de um wrapper/repositório para abstrair operações de cache e lock
- **Celery**: Se existe task de envio, ela deve ser localizada e integrada à nova service layer
- **shared/utils/redis_***: Importações do módulo shared devem ser consolidadas em um ponto único de infraestrutura

### Decisões de Arquitetura

#### Estrutura de Diretórios Alvo

```
notifications/
├── __init__.py
├── domain/                          # Lógica pura, sem I/O
│   ├── __init__.py
│   ├── event_detector.py            # Detecção de eventos
│   ├── snapshot_validator.py        # Validação de contrato
│   ├── price_calculator.py          # Cálculo de delta
│   ├── contact_validator.py         # Validação email/phone
│   ├── cooldown_resolver.py         # Lógica de cooldown
│   ├── deduplication.py             # Geração de hash
│   └── priority_resolver.py         # Resolução de prioridade
├── infra/                           # Encapsulamento de infra externa
│   ├── __init__.py
│   ├── redis_repository.py          # Abstração Redis
│   └── notification_locks.py        # Locks isolados
├── evaluator.py                     # Simplificado - só orquestra domínio
├── services_notifications.py        # Service Layer
├── template_renderer.py             # Mantém (já está OK)
├── channels/                        # Mantém (já está OK)
└── templates/                       # Mantém (já está OK)
```

---

## Plano de Implementação (Checklist)

### Fase 1: Extração de Validadores e Utilitários de Domínio

#### Tarefa 1.1 — Criar estrutura de diretório `domain/`
- [ ] Criar pasta `notifications/domain/`
- [ ] Criar `notifications/domain/__init__.py` vazio

#### Tarefa 1.2 — Extrair validação de snapshot
- [ ] Criar `notifications/domain/snapshot_validator.py`
- [ ] Mover função `validate_snapshot_contract()` do `evaluator.py` para `snapshot_validator.py`
- [ ] Remover dependência de `structlog` dentro da função de domínio (retornar tupla `(bool, list[str])` com sucesso e erros)
- [ ] Atualizar imports no `evaluator.py` para usar a nova localização

#### Tarefa 1.3 — Extrair validações de contato (email/telefone)
- [ ] Criar `notifications/domain/contact_validator.py`
- [ ] Mover `_is_valid_email()` e `_is_valid_phone_number()` do `evaluator.py`
- [ ] Renomear para `validate_email()` e `validate_phone_number()` (remover underscore de privacidade)
- [ ] Manter dependência de `email_validator` (é biblioteca de validação, aceitável em domínio)
- [ ] Remover duplicações do `crud_notifications.py` (se houver)

#### Tarefa 1.4 — Extrair cálculo de delta de preço
- [ ] Criar `notifications/domain/price_calculator.py`
- [ ] Mover `_price_delta_below_min()` do `evaluator.py`
- [ ] Renomear para `calculate_price_delta_percent()` - retornar o valor do delta, não boolean
- [ ] Criar função auxiliar `is_delta_below_threshold()` que compara com threshold do settings
- [ ] Atualizar imports no `evaluator.py`

#### Tarefa 1.5 — Extrair detecção de eventos
- [ ] Criar `notifications/domain/event_detector.py`
- [ ] Mover `_resolve_event_types()` do `evaluator.py`
- [ ] Renomear para `detect_events_from_snapshots()`
- [ ] Garantir que função é pura (sem dependências externas)

#### Tarefa 1.6 — Extrair mapeamento evento→alerta
- [ ] No mesmo arquivo `event_detector.py`, mover `_resolve_alert_type()`
- [ ] Renomear para `map_event_to_alert_type()`

---

### Fase 2: Criação da Camada de Domínio (Regras de Negócio)

#### Tarefa 2.1 — Extrair lógica de cooldown
- [ ] Criar `notifications/domain/cooldown_resolver.py`
- [ ] Mover `_cooldown_seconds()` do `evaluator.py`
- [ ] Renomear para `resolve_cooldown_seconds()`
- [ ] Mover `_within_cooldown()` do `evaluator.py`
- [ ] Renomear para `is_within_cooldown()`
- [ ] Garantir que ambas as funções são puras (recebem objetos AlertRule/Preference como dicts ou dataclasses, não Models SQLAlchemy)

#### Tarefa 2.2 — Extrair lógica de deduplicação
- [ ] Criar `notifications/domain/deduplication.py`
- [ ] Mover `_build_dedup_hash()` do `evaluator.py`
- [ ] Renomear para `generate_dedup_hash()`
- [ ] Garantir função pura (sem dependências externas)

#### Tarefa 2.3 — Extrair lógica de prioridade
- [ ] Criar `notifications/domain/priority_resolver.py`
- [ ] Mover `_resolve_priority()` do `evaluator.py`
- [ ] Renomear para `resolve_priority()`
- [ ] Garantir função pura

#### Tarefa 2.4 — Extrair resolução de destino de canal
- [ ] Criar `notifications/domain/channel_resolver.py`
- [ ] Mover `_resolve_channel_destination()` do `evaluator.py`
- [ ] Renomear para `resolve_channel_destination()`
- [ ] Mover `_is_channel_confirmed()` do `evaluator.py`
- [ ] Renomear para `is_channel_confirmed()`
- [ ] Garantir funções puras (recebem User como dict ou DTO, não Model SQLAlchemy)

---

### Fase 3: Encapsulamento de Infraestrutura (Redis)

#### Tarefa 3.1 — Criar estrutura de diretório `infra/`
- [ ] Criar pasta `notifications/infra/`
- [ ] Criar `notifications/infra/__init__.py`

#### Tarefa 3.2 — Criar repositório Redis
- [ ] Criar `notifications/infra/redis_repository.py`
- [ ] Implementar classe `NotificationRedisRepository` com métodos:
  - `has_key(key: str) -> bool` — encapsula `_redis_has_key()`
  - `set_dedup_marker(dedup_hash: str, ttl_seconds: int) -> bool`
  - `set_cooldown_marker(monitored_id, channel, event_type, ttl_seconds) -> bool`
  - `has_dedup_marker(dedup_hash: str) -> bool`
  - `has_cooldown_marker(monitored_id, channel, event_type) -> bool`
- [ ] Consolidar importações de `shared.utils.redis_client` neste arquivo único

#### Tarefa 3.3 — Criar wrapper de locks
- [ ] Criar `notifications/infra/notification_locks.py`
- [ ] Implementar classe `NotificationLockManager` com métodos:
  - `acquire_lock(dedup_hash: str, ttl_seconds: int) -> tuple[bool, str | None]`
  - `release_lock(lock_owner: str) -> bool`
- [ ] Consolidar importações de `shared.utils.redis_locks` neste arquivo único

#### Tarefa 3.4 — Criar funções auxiliares para chaves Redis
- [ ] No `redis_repository.py`, criar métodos privados:
  - `_dedup_key(dedup_hash: str) -> str`
  - `_cooldown_key(monitored_id, channel, event_type) -> str`
- [ ] Mover lógica de construção de chaves do `crud_notifications.py`

---

### Fase 4: Simplificação do CRUD (Apenas Persistência)

#### Tarefa 4.1 — Remover lógica de negócio do `create_notification()`
- [ ] Abrir `crud/crud_notifications.py`
- [ ] Identificar todas as validações de negócio em `create_notification()`
- [ ] Remover verificações de dedup, cooldown, locks de dentro da função
- [ ] Transformar `create_notification()` em uma função simples que apenas:
  - Recebe parâmetros validados
  - Cria objeto `Notification`
  - Persiste no banco via `db.add()` e `db.commit()`
- [ ] Retornar sempre `Notification`, nunca `None` (se houver erro, lançar exceção)

#### Tarefa 4.2 — Remover funções duplicadas de validação
- [ ] Remover `_resolve_channel_destination()` se existir
- [ ] Remover `_is_valid_email()` se existir
- [ ] Remover `_is_valid_phone_number()` se existir
- [ ] Remover `_is_channel_confirmed()` se existir
- [ ] Remover `_cooldown_seconds()` se existir
- [ ] Remover `_within_cooldown()` se existir
- [ ] Remover `_build_dedup_hash()` se existir
- [ ] Remover `_resolve_priority()` se existir

#### Tarefa 4.3 — Remover operações Redis do CRUD
- [ ] Remover funções `_redis_has_key()`, `_dedup_key()`, `_cooldown_key()`
- [ ] Remover funções `_has_recent_sent_notification()`, `_has_dedup_in_window()`
- [ ] Remover importações de `shared.utils.redis_client` e `shared.utils.redis_locks`
- [ ] CRUD agora opera apenas no banco de dados PostgreSQL

#### Tarefa 4.4 — Simplificar `get_pending_notifications()`
- [ ] Garantir que função apenas consulta banco sem lógica de negócio
- [ ] Manter filtros de status e ordenação por prioridade/data

#### Tarefa 4.5 — Simplificar `mark_notification_sent()`
- [ ] Remover lógica de cooldown Redis de dentro da função
- [ ] Apenas atualizar campos no banco: `status`, `sent_at`, `cooldown_expires_at`

---

### Fase 5: Criação da Service Layer (Orquestrador)

#### Tarefa 5.1 — Criar arquivo de serviço
- [ ] Criar `notifications/services_notifications.py` na raiz do módulo `notifications/`

#### Tarefa 5.2 — Implementar função de orquestração de avaliação
- [ ] Criar função `evaluate_and_create_notifications()`
- [ ] Função recebe:
  - `monitored: MonitoredProduct`
  - `previous_snapshot: dict`
  - `current_snapshot: dict`
  - `user: User`
  - `db: Session`
- [ ] Fluxo interno:
  1. Buscar preferências e regras do usuário via CRUD
  2. Chamar `evaluator.evaluate()` para gerar lista de `NotificationCandidate`
  3. Para cada candidato:
     - Verificar dedup via `redis_repository.has_dedup_marker()`
     - Verificar cooldown via `redis_repository.has_cooldown_marker()`
     - Se passou, adquirir lock via `notification_locks.acquire_lock()`
     - Criar evento via `crud.create_event_log()`
     - Criar notificação via `crud.create_notification()` (simplificado)
     - Marcar dedup e cooldown no Redis via `redis_repository.set_*_marker()`
     - Liberar lock via `notification_locks.release_lock()`
  4. Retornar lista de IDs de notificações criadas

#### Tarefa 5.3 — Implementar função de processamento de notificações pendentes
- [ ] Criar função `process_pending_notifications()`
- [ ] Função recebe:
  - `db: Session`
  - `limit: int` (quantidade de notificações a processar)
- [ ] Fluxo interno:
  1. Buscar notificações pendentes via `crud.get_pending_notifications()`
  2. Para cada notificação:
     - Adquirir lock de processamento via `crud.acquire_notification_for_processing()`
     - Chamar adapter apropriado (via mapeamento `channel → adapter`)
     - Renderizar template via `template_renderer.render_notification()`
     - Registrar tentativa via `crud.add_notification_attempt()`
     - Atualizar status via `crud.mark_notification_sent()` ou `mark_notification_failed()`
     - Marcar cooldown no Redis se enviado com sucesso
  3. Retornar estatísticas de processamento

#### Tarefa 5.4 — Criar funções auxiliares de mapeamento
- [ ] Criar dicionário `CHANNEL_TO_ADAPTER` mapeando `NotificationChannel` para classes de adapter
- [ ] Criar função `_get_adapter_for_channel(channel: NotificationChannel)`

---

### Fase 6: Simplificação do Evaluator

#### Tarefa 6.1 — Refatorar `evaluator.py` para usar módulos de domínio
- [ ] Remover todas as funções privadas (`_*`) que foram extraídas
- [ ] Atualizar função `evaluate()` para:
  - Importar e usar `snapshot_validator.validate_snapshot_contract()`
  - Importar e usar `event_detector.detect_events_from_snapshots()`
  - Importar e usar `price_calculator.is_delta_below_threshold()`
  - Importar e usar `channel_resolver.resolve_channel_destination()`
  - Importar e usar `contact_validator.validate_email()`, `validate_phone_number()`
  - Importar e usar `channel_resolver.is_channel_confirmed()`
  - Importar e usar `cooldown_resolver.resolve_cooldown_seconds()`
  - Importar e usar `deduplication.generate_dedup_hash()`
  - Importar e usar `priority_resolver.resolve_priority()`
  - Importar e usar `template_renderer.render_notification()`

#### Tarefa 6.2 — Ajustar `NotificationCandidate` para remover detalhes de implementação
- [ ] Analisar campos atuais de `NotificationCandidate`
- [ ] Remover `dedup_hash` do dataclass (deve ser gerado na service layer, não exposto)
- [ ] Remover `cooldown_seconds` do dataclass (idem)
- [ ] Manter apenas campos essenciais:
  - `channel`, `event_type`, `recipient`, `subject`, `message`, `payload`, `priority`
  - `alert_rule`, `preference` (opcionais para rastreamento)

#### Tarefa 6.3 — Adicionar log estruturado no evaluator
- [ ] Garantir que `evaluate()` loga decisões importantes:
  - Snapshots inválidos
  - Eventos detectados
  - Canais sem destinatário válido
  - Candidatos criados com sucesso

---

### Fase 7: Ajustes Finais e Correções

#### Tarefa 7.1 — Corrigir typo no modelo `EventLog`
- [ ] Abrir `models/models_notifications.py`
- [ ] Renomear campo `ocurred_at` para `occurred_at` (adicionar 'r')
- [ ] Criar migração Alembic para renomear coluna no banco
- [ ] Atualizar todas as referências no código (CRUD, schemas, etc.)

#### Tarefa 7.2 — Centralizar constantes de domínio
- [ ] Criar `notifications/domain/constants.py`
- [ ] Mover constantes:
  - `DEFAULT_MAX_ATTEMPTS = 3`
  - `DEFAULT_DEDUPE_SENT_WINDOW_SECONDS = 60 * 10`
  - `DEFAULT_COOLDOWN_SECONDS` (importar de settings se aplicável)
  - `DEFAULT_CHANNEL_SETTINGS` (dicionário de canais habilitados)
- [ ] Atualizar imports em CRUD, service layer e evaluator

#### Tarefa 7.3 — Verificar e padronizar uso de Enums
- [ ] Localizar arquivo `enums/enums_notifications.py` (não anexado, precisa verificar)
- [ ] Garantir que `EventType`, `AlertType`, `NotificationChannel`, `NotificationStatus`, `DeliveryStatus` estão bem definidos
- [ ] Padronizar uso: sempre usar o Enum diretamente, nunca `.value` exceto em logs

#### Tarefa 7.4 — Atualizar rotas se necessário
- [ ] Verificar se `routes/routes_notifications.py` precisa chamar nova service layer
- [ ] Se houver endpoints que criam notificações diretamente, refatorar para usar `services_notifications.evaluate_and_create_notifications()`
- [ ] Manter endpoints de listagem e preferências como estão

#### Tarefa 7.5 — Atualizar schemas se necessário
- [ ] Revisar `schemas/schemas_notifications.py`
- [ ] Ajustar `NotificationCreate` se estrutura mudou
- [ ] Garantir que schemas refletem modelo após correção do typo

---

### Fase 8: Integração com Tasks Celery (Se Existir)

#### Tarefa 8.1 — Localizar tasks Celery de notificações
- [ ] Buscar em `tasks/` por tasks relacionadas a notificações
- [ ] Identificar onde `evaluator.evaluate()` é chamado atualmente
- [ ] Identificar task que processa notificações pendentes (se houver)

#### Tarefa 8.2 — Refatorar tasks para usar service layer
- [ ] Substituir chamadas diretas a `evaluator.evaluate()` por `services_notifications.evaluate_and_create_notifications()`
- [ ] Substituir lógica de processamento de notificações por `services_notifications.process_pending_notifications()`
- [ ] Garantir que tasks são agora cascas finas que apenas delegam para services

#### Tarefa 8.3 — Testar pipeline completa
- [ ] Simular evento que gera notificação (mudança de preço)
- [ ] Verificar que:
  - Evento é detectado
  - Candidatos são gerados
  - Dedup/cooldown funcionam
  - Notificação é persistida
  - Notificação é processada e enviada via adapter
  - Tentativa é registrada

---

## 4. Definição de Pronto (Definition of Done)

### Critérios de Conclusão

#### Estrutura
- [ ] Todos os módulos de domínio estão em `notifications/domain/`
- [ ] Infraestrutura Redis isolada em `notifications/infra/`
- [ ] Service layer existe em `notifications/services_notifications.py`
- [ ] CRUD contém apenas operações de banco de dados
- [ ] Evaluator usa apenas módulos de domínio e service

#### Funcionalidade
- [ ] Fluxo completo de notificação funciona ponta a ponta:
  - Mudança detectada → Candidatos gerados → Notificação criada → Notificação enviada
- [ ] Deduplicação funciona (mesma notificação não é enviada 2x)
- [ ] Cooldown funciona (notificações respeitam intervalo mínimo)
- [ ] Locks previnem race conditions
- [ ] Todos os canais (email, SMS, WhatsApp, push, webhook) funcionam

#### Qualidade
- [ ] CI/CD passa sem erros
- [ ] Linter (pylint, ruff) sem warnings críticos

#### Documentação
- [ ] README de notificações atualizado com nova estrutura
- [ ] CLAUDE.md reflete estado real do módulo
- [ ] Docstrings presentes em todas as funções públicas
- [ ] Diagrama de arquitetura criado (texto ou visual)

#### Performance e Observabilidade
- [ ] Logs estruturados em cada camada (domain não loga, service loga decisões)
- [ ] Métricas de latência para processamento de notificações
- [ ] Alertas configurados para notificações em dead letter queue

---

## 5. Observações de Execução

### Ordem de Execução Recomendada
Executar as fases **sequencialmente**. Não pular para Fase 5 sem concluir Fases 1-4, pois há dependências entre elas.

> Esse plano fornece um roteiro completo, incremental e acionável para refatorar a responsabilidade de **Notificações** no `market_alert`, resolvendo todos os blocos problemáticos identificados no diagnóstico.
