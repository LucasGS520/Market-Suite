# Plano de Refatoração - Ciclo de Vida dos Produtos

## Análise de Riscos e Decisões Chave
Criar uma camada `domain/` que centraliza decisões de negócio sobre produtos: agendamento, transições de status, cálculo de estabilidade. Esta camada será **agnóstica a infraestrutura** (não conhece Redusm CRUD ou banco diretamente).

Estrutura esperada:
```
market_alert/
├── crud/                    # Acesso puro a dados
│   ├── crud_monitored.py   # Apenas CRUD (sem lógica)
│   └── crud_competitor.py  # Apenas CRUD (sem lógica)
├── domain/                  # Regras de negócio (novo)
│   ├── product_lifecycle.py  # Decisões de status, agendamento
│   └── stability.py          # Cálculo de estabilidade
├── services/                # Orquestração
│   ├── services_monitored_lifecycle.py  # Criar, pausar, deletar (novo/refatorado)
│   ├── services_competitor_lifecycle.py # Criar, pausar, deletar (novo)
│   └── services_products.py             # Helper comum
└── orchestrator/            # Coordenação com filas/tasks
    └── collector_service_orchestrator.py # Enfileiramento
```

Riscos: Importações circulares ao tentar separar domain, CRUD e services.
Mitigação: Estabelecer regra clara de fluxo de dependências:
```
Tasks/Routes (entrada)
    ↓
Services (orquestração)
    ↓
Domain (regras de negócio)
    ↓
CRUD (acesso a dados)
    ↓
Models (ORM)
```
Nenhum arquivos de nível inferior deve importar de nível superior.

* Dependências:
- `interval_calculator_products.py` atual deve permanecer como utilitário de cálculo
- `price_utils.py`, `name_derivation.py` são utilitários históricos já bem feitos; não movê-los
- `collector_product_task.py` deve continuar como casca fina que delega para services
- Routes precisarão apenas chamar services, não CRUD diretamente

### Benefícios Esperados
1. **Testabilidade:** Testar regras de agendamento sem banco, Redis ou Celery
2. **Compreensão:** Novo dev identifica exatamente onde cada decisão é tomada
3. **Manutenção:** Mudança em regra de agendamento → edita um único arquivo (domain)
4. **Rastreabilidade:** Log explícito de cada operação feita pela regra

---

## Plano de Implementação

### Fase 1 — Extração de Regras de Negócio para Camada de Domínio

#### Fase 1.1 — Preparação e Análise Estrutural

- [ ] **Auditoria:** Listar todas as funções em crud_monitored.py que contêm lógica de negócio (não apenas CRUD):
  - Função `_update_price_change_tracking`
  - Função `_resolve_schedule_event`
  - Qualquer função privada que decidir estado, intervalo ou agendamento
  - Documentar exatamente qual é a regra e sua precedência

- [ ] **Auditoria:** Listar todas as funções em `services_monitored.py` que misturam responsabilidades:
  - Funções que consultam comparações E filas E concorrentes
  - Funções que validam acesso E modificam estado E retornam schema
  - Documentar o fluxo de cada função principal

- [ ] **Mapa de Dependências:** Desenhar o grafo atual de imports entre `crud_monitored`, `services_monitored`, `services_priority_queue`, `services_comparison`, `services_competitors`. Identificar ciclos ou paths complexas.

#### Fase 1.2 — Criar Módulo de Domínio para Decisões de Produto

- [ ] **Criar arquivo:** `market_alert/domain/product_lifecycle.py`
  - Este arquivo conterá apenas **funções puras** (sem efeitos colaterais, sem DB, sem Redis)
  - Responsabilidades:
    - Decidir transição de status (pending → active, active → failed, paused/resumed)
    - Decidir agendamento subsequente (próximo check_at e intervalo)
    - Validar precondições de operações (ex: só pode pausar se ativo)
  
- [ ] **Extrair função:** `resolve_scheduling_event(price_changed: bool, availability_changed: bool) -> str`
  - Remove a versão privada de `crud_monitored.py`
  - Retorna nome do evento (EVENT_PRICE_CHANGED, EVENT_AVAILABILITY_CHANGED, EVENT_STANDARD)
  - Sem dependência externa
  
- [ ] **Extrair função:** `compute_next_check_at(product: MonitoredProduct, event: str, retry_context: RetryContext | None) -> datetime`
  - Encapsula lógica atual de `interval_calculator_products.calculate_schedule()`
  - Consulta o produto em memória para decidir intervalo
  - Retorna timestamp calculado

- [ ] **Extrair função:** `validate_status_transition(current_status: MonitoredStatus, target_status: MonitoredStatus) -> bool`
  - Valida se transição é permitida (ex: não há transição de "failed" para "active" sem restart)
  
- [ ] **Criar arquivo:** `market_alert/domain/stability.py`
  - Mover função `calculate_stability_score()` atualmente em `crud_monitored.py` ou `interval_calculator_products.py`
  - Função pura que recebe um produto e retorna score (0, 1, 2)
  - Sem efeitos colaterais

- [ ] **Testes:** Criar testes unitários para `domain/product_lifecycle.py` e `domain/stability.py`
  - Não exigem banco, Redis ou Celery
  - Testam todas as combinações de evento × status × retry context

---

### Fase 2 — Limpeza e Separação da Camada CRUD

#### Fase 2.1 — Remover Lógica de Serviço do CRUD

- [ ] **Refatorar:** `crud_monitored.py`
  - [ ] Remover import de `services_priority_queue`; deixar apenas `crud_competitor`, `crud_price_history`, models e queries SQL
  - [ ] Remover funções privadas `_update_price_change_tracking`, `_resolve_schedule_event`, `_activate_pending_monitored` — estas migram para domain ou services
  - [ ] Remover imports locais dentro de funções (sintoma de dependência circular)
  - [ ] Documentar: "Este arquivo contém apenas operações de leitura e escrita. Decisões de estado ou agendamento ocorrem na camada domain ou services."

- [ ] **Refatorar:** `crud_competitor.py`
  - [ ] Aplicar mesma limpeza: remover lógica de serviço, manter apenas CRUD
  - [ ] Remover efeitos colaterais de enfileiramento

- [ ] **Refatorar:** `crud_errors.py`
  - [ ] Validar se tem lógica de negócio escondida; limpar se necessário

- [ ] **Testes:** Validar que CRUD não quebrou
  - Testes simples de create/read/update/delete sem mock
  - Testar com banco real (test database)

#### Fase 2.2 — Criar Interfaces Claras de CRUD

- [ ] **Criar:** Documentação (docstrings e README) explicando que CRUD é agnóstico a domínio
  - Listar as funções públicas esperadas
  - Indicar que efeitos colaterais devem ser tratados no nível de serviço

---

### Fase 3 — Reorganização da Camada de Serviços

#### Fase 3.1 — Quebrar services_monitored.py em Serviços Menores

- [ ] **Criar arquivo:** `market_alert/services/services_monitored_lifecycle.py`
  - Responsabilidade única: **Criar, pausar, retomar e deletar produtos monitorados**
  - Funções esperadas:
    - `create_monitored_product(db, user, product_data, request_context) -> MonitoredScrapeCreationResponse`
    - `pause_monitored(db, user, monitored_id) -> MonitoredProductResponse`
    - `resume_monitored(db, user, monitored_id) -> MonitoredProductResponse`
    - `delete_monitored(db, user, monitored_id) -> bool`
  - Cada função chama domain para validação/decisão, depois CRUD para persister, depois orchestrator se precisar enfileirar
  - Não conhece comparações, notificações ou dashboards

- [ ] **Criar arquivo:** `market_alert/services/services_competitor_lifecycle.py`
  - Responsabilidade única: **Criar, pausar e deletar produtos concorrentes**
  - Funções esperadas:
    - `create_competitor(db, user, product_data, request_context) -> CompetitorScrapeCreationResponse`
    - `pause_competitor(db, user, competitor_id) -> CompetitorProductResponse`
    - `delete_competitor(db, user, competitor_id, monitored_id) -> bool`
  - Similar a `services_monitored_lifecycle.py`, mas para concorrentes

- [ ] **Refatorar:** `services_monitored.py` (arquivo original)
  - Manter apenas funções de listagem/paginação que **não alteram estado**:
    - `list_monitored_products(db, user_id, pagination) -> PaginatedMonitoredProductsResponse`
    - `get_monitored_product(db, user, product_id) -> MonitoredProductResponse`
    - `list_featured_monitored_products(db, user_id) -> list[MonitoredProductResponse]`
  - Estas funções são **read-only** e podem coexistir com lógica de comparação se necessário

- [ ] **Refatorar:** `services_competitors.py`
  - Separar funções de listagem (read-only) das de criação/deleção
  - Lifecyle → novo arquivo, queries → permanecer.

#### Fase 3.2 — Definir Contrato Claro de Cada Service

- [ ] **Docstring centralizada:** Cada novo service file começa com uma seção que explica:
  - Qual é sua responsabilidade única
  - Quais imports ele faz (CRUD, domain, orchestrator)
  - Quais não faz (comparação, notificação, limite de taxa)
  - Exemplo de uso em uma route

---

### Fase 4 — Integração com Routes, Tasks e Orchestrator

#### Fase 4.1 — Atualizar Routes

- [ ] **Refatorar:** `routes_monitored.py`
  - [ ] Endpoint `POST /monitored/scrape` chama `services_monitored_lifecycle.create_monitored_product()`
  - [ ] Endpoint `GET /monitored/` chama `services_monitored_queries.list_monitored_products()` (ou similar)
  - [ ] Endpoint `PUT /monitored/{id}/paused` chama `services_monitored_lifecycle.pause_monitored()` ou `resume_monitored()`
  - [ ] Endpoint `DELETE /monitored/{id}` chama `services_monitored_lifecycle.delete_monitored()`
  - Validar que routes não chama CRUD diretamente; tudo passa por services

- [ ] **Refatorar:** `routes_competitors.py`
  - [ ] Endpoint `POST /competitors/scrape` chama `services_competitor_lifecycle.create_competitor()`
  - [ ] Endpoint `DELETE /competitors/{id}` chama `services_competitor_lifecycle.delete_competitor()`
  - Validar que não chama CRUD diretamente

- [ ] **Testes:** Testar cada route com chamada aos serviços refatorados
  - Mock de CRUD e domain
  - Validar request/response contracts

#### Fase 4.2 — Atualizar Orchestrator

- [ ] **Validar:** `collector_service_orchestrator.py`
  - Continua seu trabalho de construir payloads e enfileirar tasks
  - Verificar se chama CRUD diretamente; se sim, documentar por quê ou refatorar
  - Atualizar imports se `services_monitored_lifecycle` ou `services_competitor_lifecycle` mudaram de local

#### Fase 4.3 — Atualizar Tasks

- [ ] **Validar:** `collector_product_task.py`
  - Função `collect_product()` executa coleta e precisa **persistir mudanças de estado**
  - Esta função deve chamar `domain/product_lifecycle.py` para decidir próximo check_at
  - Depois chamar `crud_monitored.update()` para persistir
  - Depois chamar `orchestrator.enqueue_monitored_at()` se necessário
  - Validar que não há lógica de domínio espalhada pela task; tudo vem de `domain/`

- [ ] **Validar:** `scraper_tasks.py`
  - Remover ou atualizar se tem chamadas diretas a CRUD que desapareceram

#### Fase 4.4 — Atualizar Utils

- [ ] **Validar:** `interval_calculator_products.py`
  - Função `calculate_schedule()` já existe e é boa
  - Garantir que `domain/product_lifecycle.py` reutiliza lógica daqui ou absorve
  - Não criar duplicação

- [ ] **Validar:** `price_utils.py`, `name_derivation.py`
  - Estas são utilitários puros; não precisam de mudança

---

### Fase 5 — Validação e Testes integrados

#### Fase 5.1 — Testes Unitários de Cada Camada

- [ ] **Domain:** Testes para `product_lifecycle.py` e `stability.py`
  - Inputs: estado anterior, evento, retry context
  - Outputs: novo status, novo agendamento
  - Sem mock de DB ou Redis

- [ ] **CRUD:** Testes para crud_monitored.py e `crud_competitor.py`
  - Inputs: modelos Pydantic, IDs
  - Outputs: objetos ORM persistidos
  - Com test database real (sqlite em memória ou PostgreSQL test)

- [ ] **Services:** Testes para `services_monitored_lifecycle.py` e `services_competitor_lifecycle.py`
  - Inputs: request payloads
  - Outputs: response schemas
  - Mock de CRUD, domain, orchestrator
  - Validar chamadas entre camadas

#### Fase 5.2 — Testes de Integração

- [ ] **Fluxo ponta-a-ponta:** Teste que cria um monitorado via route e valida persistência
  - Route → Service → CRUD → Bank → Domain mantém coerência
  - Sem Celery; ignore enfileiramento por enquanto

- [ ] **Fluxo de coleta:** Mock a task `collector_product_task.collect_product()`
  - Coleta um item, chama domain para agendamento, atualiza CRUD
  - Valida que próximo check_at foi calculado corretamente

- [ ] **Fluxo de transição de estado:** Teste pausa/resume
  - Validar que transição é respeitada
  - Validar que efeitos colaterais (enfileiramento, re-comparações) são corretos

#### Fase 5.3 — Validação de Contrato

- [ ] **Compatibilidade backwards:** Validar que mudanças não quebram celery tasks, routes legadas ou testes existentes
- [ ] **Importações:** Executar script para verificar que não há ciclos de import
- [ ] **Cobertura:** Rodar coverage; objetivo mínimo 80% nas camadas novas

---

## 4. Definição de Pronto (Definition of Done)

O trabalho de refatoração está **completo** quando:

### Critérios Estruturais
- [ ] Arquivo `market_alert/domain/product_lifecycle.py` criado e testado
- [ ] Arquivo `market_alert/domain/stability.py` criado e testado
- [ ] Arquivo `market_alert/services/services_monitored_lifecycle.py` criado e testado
- [ ] Arquivo `market_alert/services/services_competitor_lifecycle.py` criado e testado
- [ ] crud_monitored.py e `crud_competitor.py` possuem apenas operações CRUD (sem lógica de domínio)
- [ ] Rotas em `routes_monitored.py` e `routes_competitors.py` chamam os novos services, nunca CRUD diretamente

### Critérios de Comportamento
- [ ] Fluxo de criação de monitorado: Route → Service → Domain (decisão) → CRUD (persistência) → Orchestrator (enfileiramento)
- [ ] Fluxo de pausa/resume: Route → Service → Domain (validação) → CRUD (persistência)
- [ ] Fluxo de deleção: Route → Service → CRUD (delete cascata) → Comparação recalcula se necessário
- [ ] Fluxo de coleta (em task): Task → Domain (próximo agendamento) → CRUD (update) → Orchestrator (reenfileira)

### Critérios de Qualidade
- [ ] Testes unitários para domain/ (mínimo 80% cobertura, sem mock de infra)
- [ ] Testes de integração para services/ (mínimo 70% cobertura, mock de camadas externas)
- [ ] Nenhuma importação cíclica (validar com script ou análise manual)
- [ ] Logging adicionado em pontos-chave de decisão (domain)

### Critérios de Documentação
- [ ] README.md atualizado com novo diagrama de fluxo de "Ciclo de Vida"
- [ ] CLAUDE.md atualizado com resultado da refatoração e próximas etapas
- [ ] Docstrings em cada novo arquivo explicando responsabilidade e contrato

### Critérios de Regressão
- [ ] Testes existentes de routes continuam passando
- [ ] Testes existentes de CRUD continuam passando
- [ ] Task `collector_product_task` continua funcionando sem alterações externas
- [ ] Sem quebra em comportamento do usuário (criar, editar, deletar monitorados continua funcionando)

---

Este plano fornece um caminho claro para restaurar a arquitetura limpa do módulo `market_alert`, começando pela responsabilidade mais crítica: o ciclo de vida dos produtos. Cada fase é acionável, testável e não depende de mudanças complexas no banco de dados ou esquema ORM.
