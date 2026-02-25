# Plano de Refatoração — Infraestrutura

## Análise de Riscos e Decisões Chave

### Decisão Técnica Principal
**Criar uma camada de abstração de infraestrutura em `shared/infra/` que define interfaces (protocolos Python) para Celery, logging e rate limiting, sem implementações específicas.**  
Isso permite que `market_alert` use essas interfaces sem conhecer detalhes de Celery/Redis, facilitando testes e futuras migrações.

### Riscos Principais

| Risco | Impacto | Mitigação |
|-------|--------|-----------|
| **Regressão em workers Celery** | Alto — Workers quebram, coletas param | Manter versão em branch, testar com worker real antes de merge |
| **Circular imports durante refator** | Médio — Code não roda | Resolver em paralelo com cada fase, usar imports tardios se necessário (temporário) |
| **Inconsistência de logging entre API e Worker** | Médio — Debugar difícil | Implementar configuração única antes de separar módulos |
| **Perda de dados em Redis durante migração** | Baixo — Apenas dados transitórios | Não há estado persistente em Redis que não possa ser recalculado |
| **Configuração conflitante (shared vs market_alert)** | Médio — Config inesperada | Documentar precedência clara e adicionar validação em tempo de startup |

### Decisões Secundárias

1. **Logging centralizador?** Sim — `shared/infra/logging.py` com factory que retorna logger estruturado com mesmo formato.
2. **Rate limiting é de domínio?** Não — Fica em infra, mas `bruteforce` é caso especial de "auth domain logic" (fica em auth/).
3. **Onde vai orchestrator/collection_enqueuer?** Refatorar para `infra/celery/enqueuer.py` para deixar claro que é infra, não orquestração.
4. **Retry policies — core ou orchestrator?** Mover TUDO para `infra/celery/retry_policies.py` — é infra, não core.

---

## Plano de Implementação (Checklist)

### **FASE 1: Infraestrutura Compartilhada (shared/) — Fundação**

#### 1.1 Criação de Abstrações de Infra em shared/

- [ ] **Criar arquivo `shared/infra/logging.py`**
  - Definir função `configure_structlog(service_name: str, environment: str) -> None`
  - Centralizar processadores JSON, formatadores, handlers para estrutlog
  - Suportar diferentes níveis de log para diferentes módulos (ex: silenciar celery.*, libcurl)
  - Retornar logger pré-configurado para reutilização

- [ ] **Criar arquivo `shared/infra/rate_limiter.py`**
  - Definir classe abstrata/interface `RateLimiter` (ou Protocol)
  - Métodos: `check(key: str, max_attempts: int, window_seconds: int) -> bool`
  - Implementação concreta: `RedisRateLimiter` que usa Redis
  - Permitir injeção de dependência em testes

- [ ] **Criar arquivo `shared/infra/celery_interface.py`**
  - Definir Protocol/Interface para operações básicas: `send_task()`, `retry()`
  - Encapsular `CeleryBroker` que wraps `celery_app` sem expor detalhes

#### 1.2 Consolidação de Configuração Compartilhada

- [ ] **Refatorar `shared/core/config_base.py`**
  - Mover constantes de logging (níveis, formatos) para `Settings`
  - Adicionar `LOG_LEVEL: str = "INFO"`, `LOG_FORMAT: str = "json"`
  - Consolidar Circuit Breaker, Redis, Brute Force em um único lugar
  - Documentar que `config_base` é "read-only" — valores defaults apenas

- [ ] **Ajustar .env.common** na raiz (já existe)
  - Valores compartilhados entre `market_alert` e `market_scraper`
  - Exemplo: `REDIS_HOST`, `LOG_LEVEL`, `CIRCUIT_FAILURES_KEY`, entre outras variáveis ESSENCIAIS.

---

### **FASE 2: Refatoração do Core (market_alert/core/) — Separação de Responsabilidades**

#### 2.1 Desmembramento de celery_app.py

- [ ] **Criar arquivo `market_alert/infra/celery_config.py`**
  - Mover: Definição de TASK_MODULES, TASK_QUEUES, TASK_ROUTES (atualmente em `celery_schedule.py`)
  - Mover: Configurações de serialização, timezone, concurrency de `celery_app.py`
  - Mover: Exchanges, Queues definitions
  - **Responsabilidade única:** Decorações de configuração do Celery

- [ ] **Criar arquivo `market_alert/infra/celery_init.py`**
  - Mover: Criação da instância `celery_app`
  - Mover: Carregamento de task_modules
  - Função `create_celery_app(config: celery_config) -> Celery`
  - **Responsabilidade única:** Bootstrap da app Celery

- [ ] **Criar arquivo `market_alert/infra/worker_lifecycle.py`**
  - Mover: Implementação de `@worker_ready.connect` e lógica de autostart
  - Mover: Lógica de cooldown, verificação de Redis, envio de task inicial
  - Função `register_worker_signals(celery_app: Celery, config: Settings) -> None`
  - **Responsabilidade única:** Gerenciar hooks de lifecycle do worker

- [ ] **Criar arquivo `market_alert/core/logging_config.py`**
  - Mover: `configure_logging()` de main.py
  - Mover: `configure_worker_logging()` de celery_app.py
  - Usar factory de `shared/infra/logging.py`
  - Função `setup_logging_for_api(service_name: str) -> None`
  - Função `setup_logging_for_worker(service_name: str) -> None`

- [ ] **Refatorar arquivo `market_alert/core/celery_app.py`** (reduzir escopo)
  - Manter: Apenas imports e criação da instância `celery_app`
  - Delegar: tudo para modules acima
  - Resultado esperado: **~15 linhas**, não >300

- [ ] **Remover arquivo `market_alert/core/celery_schedule.py`** (consolidado)
  - Mover conteúdo para `market_alert/infra/celery_config.py`

#### 2.2 Unificação de Retry Policies

- [ ] **Criar arquivo `market_alert/infra/celery/retry_policies.py`**
  - Consolidar: `core/retry_policies.py` + `orchestrator/retry_policy.py`
  - Estrutura:
    - Constantes de política (LOCK_RETRY_MAX_RETRIES, etc.) no topo
    - Classe `RetryPolicy` com métodos estáticos para decisões
    - Dicts de policy nomeados para uso em decorators (@celery_app.task)
  - **Responsabilidade única:** Centralize TODAS as decisões e constantes de retry

- [ ] **Remover duplicação**
  - Excluir: `core/retry_policies.py`
  - Excluir: `orchestrator/retry_policy.py`
  - Atualizar imports em tasks, serviços

#### 2.3 Refatoração de Rate Limiting

- [ ] **Refatorar `core/bruteforce.py`**
  - Renomear para `auth/rate_limiter_auth.py` (é specific da autenticação)
  - Mover lógica genérica para `shared/infra/rate_limiter.py`
  - Usar `RateLimiter` injected como dependência
  - Implementação agora é clean: apenas "record_failed_attempt", "block_ip", etc.

- [ ] **Refatorar `main.py`**
  - Mover: Configuração de `SlowAPIMiddleware` para função `setup_middleware_rate_limiting()`
  - Mover: Handler de erro para função `create_rate_limit_handler()`
  - Resultado: main.py fica limpo, apenas chama factory functions

- [ ] **Consolidar constantes de rate limit**
  - Mover: `SCRAPER_HOST_RATE_LIMIT`, etc. de `.env.market_alert` para `config_alert.py`
  - Adicionar defaults semanticamente corretos em código
  - Pattern: `.env` só para **overrides**, não source of truth

---

### **FASE 3: Separação de Orquestração vs Infraestrutura**

#### 3.1 Reorganização de orchestrator/

- [ ] **Criar diretório `market_alert/infra/celery/`**
  - Moveré `orchestrator/collection_enqueuer.py` para `infra/celery/enqueuer.py`
  - Mover `orchestrator/collection_queue.py` para `orchestrator/priority_queue.py` (fica orquestração)
  - **Semântica:** collection_enqueuer = como chamar Celery (infra), collection_queue = quando chamar (orquestração)

- [ ] **Refatorar `infra/celery/enqueuer.py`** (antes collection_enqueuer)
  - Remover: Direct import de `celery_app`
  - Adicionar: Injeção via Protocol/interface de `CeleryBroker`
  - Resultado: Testável sem instânciar Celery real

- [ ] **Refatorar `orchestrator/` (somente lógica de negócio)**
  - Manter: CollectionQueue, retry_triggers, é tudo lógica de "quando" coletar
  - Remover: qualquer detalhe de Redis, Celery, timeouts de worker
  - Comprovar: orchestrator/ não importa direto de `core/celery_app`

#### 3.2 Criação de Módulo infra/

- [ ] **Criar estrutura `market_alert/infra/`**
  ```
  infra/
    __init__.py
    celery/
      __init__.py
      config.py
      init.py
      enqueuer.py
      retry_policies.py
    # database.py importa de shared/
    redis.py
    logging_config.py
  ```

---

### **FASE 4: Consolidação de Configuração**

#### 4.1 Hierarquia de Configuração Única

- [ ] **Refatorar `market_alert/core/config_alert.py`**
  - Estruturar campos por seção lógica:
    - `class DatabaseConfig(ConfigBase)`
    - `class CeleryConfig(ConfigBase)`
    - `class NotificationConfig(ConfigBase)`
    - `class SecurityConfig(ConfigBase)`
    - etc.
  - Adicionar validação: `@model_validator` para garantir valores obrigatórios
  - Documentar ordem de precedência: defaults (código) → shared/config_base → .env.common → `.env.market_alert`

- [ ] **Atualizar `.env.market_alert`**
  - Remover constantes com defaults sensatos (ex.: `ALGORITHM=HS256`)
  - Manter apenas: valores sensitivos (tokens, URLs), valores específicos do ambiente
  - Comentar cada seção

#### 4.2 Validação de Startup

- [ ] **Criar função `market_alert/core/startup_validation.py`**
  - Verificar: Todas as configurações críticas estão presentes
  - Verificar: Conectividade com Redis, PostgreSQL na startup
  - Logar: Warnings se configurações de ambiente estão no "desenvolvimento"
  - Usar: Em `main.py` e em worker lifecycle

---

### **FASE 5: Limpeza e Consolidação Final**

#### 5.1 Artefatos de Runtime

- [ ] **Atualizar .gitignore da raiz**
  - Adicionar: `**/celerybeat-schedule`
  - Adicionar: `**/logs/`
  - Adicionar: `**/*.pid`
  - Adicionar: `**/tmp/`

- [ ] **Remover do repositório** (depois de comitado em .gitignore)
  - celerybeat-schedule
  - logs (exceto estrutura base se necessário)

#### 5.2 Verificação Final e Refatoração Cruzada

- [ ] **Audit de imports**
  - Confirmar: Nenhum `orchestrator` importa de `core/celery_app` direto
  - Confirmar: `services/` não importam `celery_app`, usam injeção ou`infra/celery/enqueuer`
  - Confirmar: `routes/` não sabem sobre Celery

- [ ] **Remover imports posteriores (E402)**
  - `celery_app.py` não deve ter `# noqa: E402`
  - Refatorar estrutura se isso for necessário

- [ ] **Compilar documentation do projeto**
  - Atualizar `README.md` com nova estrutura
  - Adicionar diagrama ASCII: camadas + direção de dependência

---

## 4. Definição de Pronto (Definition of Done)

**Marcos técnicos:**
- [ ] Nenhum arquivo de infra em market_alert tem >100 linhas
- [ ] Cada arquivo tem uma responsabilidade testável
- [ ] Zero imports posteriores (`# noqa: E402`)
- [ ] Rate limiting é usado via interface única (não 3 abstrações)
- [ ] Logging é configurado em um único lugar (factory pattern)
- [ ] `orchestrator/` não importa `celery_app` diretamente
- [ ] Retry policies são definidas uma única vez
- [ ] .gitignore inclui artefatos de runtime

**Documentação:**
- [ ] Exemplos de uso em comentários de code
- [ ] Nenhuma "magia" sem documentação inline

---

## Sequência Recomendada de Execução

1. **FASE 1** → Deploy intermediária não necessário, apenas fundação
2. **FASE 2** → Testar com worker real após cada sub-tarefa
3. **FASE 3** → Testar enfileiramento de jobs
4. **FASE 4** → Validações de startup
5. **FASE 5** → Documentação final, cleanup
