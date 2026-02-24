# PLANO DE REFATORAÇÃO — Responsabilidade "Comparação de Preços"

## Análise de Riscos e Decisões Chave

### Decisões Técnicas Principais

| Decisão | Racional | Risco |
|---------|----------|-------|
| **Extrair `domain/price_competitiveness.py`** | Concentra todas as regras de cálculo em um único lugar, independente de ORM/persistência. Permite testes unitários puros sem mockar banco. | Mudança de contrato pode impactar notificações que dependem de snapshots. Mitigado: criar adapter entre snapshot e domínio. |
| **Criar `PriceComparisonCalculator` como classe de domínio** | Encapsula estado imutável (thresholds, moeda) e operações puras (calcular status). Testável. | Aumenta número de classes. Mitigado: nomeação clara, docstrings explícitas. |
| **Separar `SnapshotComparator` como utilitário** | Idempotência fica isolada, reutilizável, testável. | Novo arquivo = nova dependência. Mitigado: sem dados de negócio, apenas comparação estrutural. |
| **Unificar entrada em `compare_prices` genérico** | Um ponto de entrada que aceita `monitored_id` e opcionalmente `tolerance`. | Pode quebrar tasks legadas. Mitigado: criar wrapper compatível temporário. |
| **Mover constantes para `config_alert.py`** | Torna thresholds configuráveis sem recompilação. Auditoria de mudanças. | Aumenta arquivo de config. Mitigado: criar grupo `COMPETITIVENESS_*` bem nomeado. |

### Riscos Principais

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|--------|-----------|
| **Notificações quebram** (dependem de snapshot) | Alta | Alto | Criar adapter `ComparisonSnapshot` que valida contrato esperado; adicionar testes de integração antes de fazer merge |
| **Regressão em edge cases** (ex: preço nulo) | Média | Alto | Manter testes de integração legados rodando em paralelo; adicionar testes parametrizados para cada cenário |
| **Performance** (novas abstrações = mais calls) | Baixa | Médio | Perfilar antes/depois; lazy-load snapshots antigos; cache de `CompetitivenessRule` |
| **Sincronização de tasks** (compare_prices_task vs HTTP) | Média | Médio | Testar ambas as rotas em paralelo; adicionar lock Redis se necessário |
| **Dependência circular** (domínio → utils) | Baixa | Médio | Revisar imports; mover constantes para enums se necessário |

---

## Plano de Implementação (Checklist)

### **FASE 1: Extração da Camada de Domínio**
Criar arquivo `domain/price_competitiveness.py` com regras de cálculo isoladas de persistência.

- [ ] **Novo Arquivo:** Criar `backend/market_alert/domain/price_competitiveness.py` com:
  
  - [ ] **Classe:** `CompetitivenessThresholds` (dataclass imutável)
    - [ ] Atributos: `non_competitive_pct: Decimal`, `attention_pct: Decimal`
    - [ ] Método: `from_config(settings)` — lê de `core/config_alert.py`
    - [ ] Docstring explicando o significado (ex: "não_competitivo = 1%, atenção = 5%")
    - [ ] `__repr__` para logging

  - [ ] **Classe:** `ComparisonSnapshot` (dataclass)
    - [ ] Atributos: `monitored_price: Decimal | None`, `competitor_prices: list[Decimal]`, `competitor_availability: list[bool] | None`
    - [ ] Método: `is_valid() -> bool` — valida se há dados suficientes
    - [ ] Método: `available_prices() -> list[Decimal]` — filtra preços válidos

  - [ ] **Classe:** `CompetitivenessResult` (dataclass)
    - [ ] Atributos: `status: CompetitivenessStatus`, `monitored_price: Decimal`, `min_price: Decimal | None`, `mean_price: Decimal | None`, `max_price: Decimal | None`, `rank: int | None`, `adjustment: Decimal | None`, `details: dict`
    - [ ] Método: `to_dict() -> Dict[str, Any]` — serializa para snapshot

  - [ ] **Função Pura:** `calculate_competitiveness(snapshot: ComparisonSnapshot, thresholds: CompetitivenessThresholds) -> CompetitivenessResult`
    - [ ] Validação de entrada (raise se snapshot inválido)
    - [ ] Cálculo de min/mean/max das disponíveis
    - [ ] Cálculo de rank (posição do monitorado)
    - [ ] Cálculo de ajuste potencial contra mínimo
    - [ ] Determinação de status (COMPETITIVE, ATTENTION, URGENT)
    - [ ] Sem lógica de persistência, sem acesso a ORM
    - [ ] Docstring com exemplos de uso

  - [ ] **Função Pura:** `determine_competitiveness_status(delta_percent: Decimal, thresholds: CompetitivenessThresholds) -> CompetitivenessStatus`
    - [ ] Helper isolado para lógica de threshold
    - [ ] Testável sem mocking

  - [ ] **Constantes:** Remover de services_comparison.py e importar daqui:
    - [ ] Valores padrão de thresholds (se config não estiver disponível)

- [ ] **Refatoração:** Em core/config_alert.py:
  - [ ] Adicionar se não existir:
    ```python
    COMPETITIVENESS_THRESHOLD_NON_COMPETITIVE_PCT: Decimal = Decimal("1")
    COMPETITIVENESS_THRESHOLD_ATTENTION_PCT: Decimal = Decimal("5")
    COMPETITIVENESS_THRESHOLD_URGENT_PCT: Decimal = Decimal("20")  # novo
    ```
  - [ ] Adicionar docstring explicando significado
  - [ ] Opcional: Permitir override via variáveis de ambiente

---

### **FASE 2: Extração de Utilitário de Snapshots (Idempotência)**
Isolar o mecanismo de comparação de snapshots para reutilização.

- [ ] **Novo Arquivo:** Criar `backend/market_alert/utils/snapshot_comparator.py` com:

  - [ ] **Função:** `extract_material_snapshot(summary_data: Dict) -> Dict[str, Any]`
    - [ ] Move lógica de `_build_material_summary_snapshot` daqui
    - [ ] Extrai apenas campos "materiais" (aqueles que indicam mudança real)
    - [ ] Docstring listando quais campos são considerados materiais

  - [ ] **Função:** `snapshot_has_changed(current: Dict, previous: Dict | None) -> bool`
    - [ ] Compara snapshots materiais
    - [ ] Retorna `True` se há mudança significativa
    - [ ] Retorna `True` se `previous` é `None`

---

### **FASE 3: Refatoração de CRUD**
Garantir que CRUD não contém lógica de comparação/persistência condicional.

- [ ] **Arquivo:** Em crud_comparison.py:

  - [ ] **Remover:** Qualquer lógica condicional que decida "se persistir"
    - [ ] Se houver validação de negócio (ex: "só persiste se competitividade mudou"), extrair para serviço
  
  - [ ] **Renomear funções para clareza:**
    - [ ] `create_price_comparison_summary` → `insert_comparison_summary` (explica que INSERE sempre)
    - [ ] `upsert_price_comparison_summary` → `upsert_comparison_summary` (simplifica)
    - [ ] Adicionar docstring: "Esta função SEMPRE persiste ou atualiza. Lógica condicional fica a cargo do caller."

  - [ ] **Adicionar tipo de retorno explícito:**
    - [ ] Adicionar `-> Tuple[PriceComparisonSummary, bool]` indicando se foi inserido ou atualizado

  - [ ] **Seu responsável:** Em services_comparison.py, a função `persist_rebuilt_summary_if_needed` é quem decide IF persistir
    - [ ] Não mover lógica; apenas documentar a separação de responsabilidades

---

### **FASE 4: Decomposição de Services — Parte A (Extração de Utilitários)**
Separar funções utilitárias de orquestração em services_comparison.py.

- [ ] **Novo Arquivo:** Criar `backend/market_alert/services/services_comparison_utils.py` com:

  - [ ] **Função:** `ensure_user_can_view_monitored_for_comparison(db, monitored_id, user) -> None`
    - [ ] Move de services_comparison.py linha ~54-62
    - [ ] Apenas verifica acesso, levanta exceção se não permitido

  - [ ] **Função:** `load_monitored_and_competitors(db: Session, monitored_id: UUID) -> Tuple[MonitoredProduct, List[CompetitorProduct]]`
    - [ ] Combina `_load_and_filter_competitors` + busca do monitorado
    - [ ] Validações de status (ativo? indisponível?)
    - [ ] Retorna: (monitorado, concorrentes_filtrados)

  - [ ] **Função:** `load_latest_snapshot(db: Session, monitored_id: UUID) -> Dict | None`
    - [ ] Lê `PriceComparisonSummary` mais recente
    - [ ] Extrai `aggregates` JSON
    - [ ] Retorna `None` se não existe

- [ ] **Em services_comparison.py:** Substituir imports diretos por chamadas para a nova função
  - [ ] Importar `ensure_user_can_view_monitored_for_comparison`
  - [ ] Importar `load_monitored_and_competitors`
  - [ ] Remover funções inlineadas

---

### **FASE 5: Decomposição de Services — Parte B (Cálculo Isolado)**
Crear função que apenas CALCULA, sem persistência.

- [ ] **Novo Arquivo:** Criar `backend/market_alert/services/services_comparison_calculator.py` com:

  - [ ] **Classe:** `MonitoredProductComparator`
    - [ ] Construtor: `__init__(thresholds: CompetitivenessThresholds, db: Session)`
    - [ ] Método: `compare_against_competitors(monitored: MonitoredProduct, competitors: List[CompetitorProduct]) -> Dict[str, Any]`
      - [ ] Valida disponibilidade/preço do monitorado
      - [ ] Coleta preços dos concorrentes (via query `PriceHistory`)
      - [ ] Cria `ComparisonSnapshot`
      - [ ] Chama `calculate_competitiveness()` do domínio
      - [ ] Transforma resultado para formato compatível com schema
      - [ ] Retorna dicionário estruturado (NÃO serializado)
    - [ ] Sem persistência, sem autorização — apenas cálculo

  - [ ] **Função Helper:** `_collect_competitor_prices(db, competitor_ids) -> Dict[UUID, Decimal | None]`
    - [ ] Lê `PriceHistory` para cada concorrente (última entrada)
    - [ ] Retorna mapa de competitor_id → preço

---

### **FASE 6: Decomposição de Services — Parte C (Orquestração e Persistência)**
Refatorar services_comparison.py para orquestrar sem lógica de cálculo.

- [ ] **Em services_comparison.py:**

  - [ ] **Remover função:** `rebuild_summary_from_current_state` (linhas ~212-320)
    - [ ] Substituído por: `_calculate_fresh_comparison(db, monitored, competitors) -> Dict`
    - [ ] Esta nova função apenas chama `MonitoredProductComparator.compare_against_competitors()`
    - [ ] Sem snapshot anterior, sem comparação de idempotência

  - [ ] **Refatorar função:** `persist_rebuilt_summary_if_needed` (linhas ~156-203)
    - [ ] Dividir em duas responsabilidades:
      - [ ] `_should_persist_summary(current_snapshot, previous_snapshot) -> bool`
        - [ ] Usa `snapshot_has_changed()` do utilitário
        - [ ] Retorna booleano
      - [ ] `_persist_summary_to_db(db, comparison_result, monitored_id) -> PriceComparisonSummary`
        - [ ] Toma resultado de comparação e ID
        - [ ] Chama `upsert_comparison_summary` do CRUD
        - [ ] Retorna objeto persistido
    
  - [ ] **Refatorar função:** `run_price_comparison` (linhas ~420-481)
    - [ ] Simplificar para um fluxo claro:
      1. Validar autorização (via utils)
      2. Carregar monitorado e concorrentes (via utils)
      3. Calcular comparação (via `MonitoredProductComparator`)
      4. Carregar snapshot anterior (via utils)
      5. Verificar se deve persistir (via nova função)
      6. Se sim, persistir (via nova função)
      7. Retornar resultado em formato esperado (sem transformação extra)
    - [ ] Adicionar docstring: "Ponto de entrada único para comparação de preços"

  - [ ] **Nova função:** `compare_prices_for_monitored(db: Session, monitored_id: UUID, user: User, tolerance: Decimal | None = None) -> Dict[str, Any]`
    - [ ] Wrapper genérico que chama `run_price_comparison` internamente
    - [ ] Aceita parâmetro `tolerance` para override de threshold
    - [ ] Docstring: "Função genérica de comparação, usada por HTTP, tasks e orquestrador"

  - [ ] **Remover ou renomear:** Funções auxiliares redundantes
    - [ ] `_persist_comparison_result` (linha ~378-412) — se sua lógica foi movida, remover
    - [ ] `_load_and_filter_competitors` — substituído por utils

  - [ ] **Adicionar LOGS:**
    - [ ] Log ao início de comparação: monitored_id, quantos concorrentes
    - [ ] Log ao persistir: se foi inserido ou não
    - [ ] Log de erros com contexto completo

---

### **FASE 7: Unificação de Pontos de Entrada**
Garantir que HTTP, tasks e orquestrador usam o mesmo fluxo.

- [ ] **Em routes_comparisons.py:**

  - [ ] **Rota GET `/comparisons/{monitored_id}/summary`:**
    - [ ] Usar `compare_prices_for_monitored()` do serviço (função unificada)
    - [ ] Se a rota altera behavior, documentar por quê

  - [ ] **Rota GET `/comparisons/{monitored_id}`:**
    - [ ] Usar mesmo de `get_paginated_comparisons_for_user()` (apenas lê histórico, OK)

  - [ ] **Rota GET `/comparisons/detail/{comparison_id}`:**
    - [ ] Garantir que schema retornado é idêntico ao do `PriceComparisonResponse`

- [ ] **Em tasks/compare_prices_task.py:**

  - [ ] **Task:** `compare_prices_task(monitored_id, user_id, ...)`
    - [ ] Usar `compare_prices_for_monitored()` do serviço
    - [ ] Task é casca fina — apenas chama serviço
    - [ ] Adicionar try/except com logging de erro
    - [ ] Retornar resultado ou exceção (para rastreamento)

  - [ ] **Criar compatibilidade:**
    - [ ] Se task legada era `@app.task`, manter mesmo nome/signature
    - [ ] Adicionar comentário de deprecação: "Use compare_prices_for_monitored() diretamente"

- [ ] **Na orquestração (orchestrator/):**

  - [ ] **Verificar se há enfileiramento de comparação após coleta**
    - [ ] Se existe, garantir que invoca `compare_prices_for_monitored()`
    - [ ] Se não existe, documentar que comparação só é acionada por HTTP ou task agendada

  - [ ] **Adicionar comentário:**
    - [ ] "Comparação é acionada por: (1) HTTP /summary, (2) task agendada, (3) orquestrador pós-coleta"
    - [ ] "Todos os pontos usam: compare_prices_for_monitored()"

---

### **FASE 8: Integração com Notificações**
Validar que snapshots continua funcionando com avaliadr de notificações.

- [ ] **Em notifications/evaluator.py:**

  - [ ] **Verificar contrato de snapshot esperado:**
    - [ ] Quais campos são lidos em `_resolve_event_types(previous_snapshot, current_snapshot)`?
    - [ ] São os mesmos campos que `extract_material_snapshot()` exporta?
    - [ ] Se não, há discrepância — documentar e resolver

  - [ ] **Adicionar validação:**
    - [ ] Criar função `validate_snapshot_contract(snapshot: Dict) -> bool`
    - [ ] Levanta `ValueError` se campos esperados faltam
    - [ ] Chamada no início de `evaluate()`

  - [ ] **Criar adapter se necessário:**
    - [ ] Se snapshot de comparação não tem exatamente os campos que notificação espera
    - [ ] Criar `ComparisonSnapshotAdapter` que transforma um para outro
    - [ ] Deixar claro na migração qual é o campo novo/removido

---

### **FASE 9: Documentação e Limpeza**
Atualizar documentação refletindo a nova arquitetura.

- [ ] **Documentação de Código:**

  - [ ] **Em cada arquivo novo/refatorado:**
    - [ ] Docstring no topo explicando responsabilidade
    - [ ] Exemplos de uso (doctest ou comentários)
    - [ ] Warnings se há dependências críticas

  - [ ] **Em market_alert/README.md:**
    - [ ] Adicionar seção "## Arquitetura da Comparação de Preços"
      - Diagrama ASCII mostrando fluxo
      - Camadas: Domínio → Serviço → CRUD
      - Exemplo de como adicionar novo threshold
    - [ ] Atualizar "Responsabilidades por Arquivo" se mudou

- [ ] **Remover Código Legado:**

  - [ ] **Em services_comparison.py:**
    - [ ] Remover constantes `COMPETITIVENESS_*_PCT` (migraram para config)
    - [ ] Remover função `_build_material_summary_snapshot` (migraram para utils)
    - [ ] Remover função `_persist_comparison_result` se foi substituída
    - [ ] Remover função `_load_and_filter_competitors` se foi substituída

  - [ ] **Verificar imports obsoletos:**
    - [ ] Se novo arquivo `services_comparison_utils.py` existe, remover imports inline
    - [ ] Atualizar `from market_alert.utils.snapshot_comparator import ...`

  - [ ] **Remover enums duplicados:**
    - [ ] Em enums_comparisons.py, remover comentário sobre duplicação se houver
    - [ ] Garantir que `CompetitivenessStatus` tem apenas um value por enum

- [ ] **Atualizar CLAUDE.md:**
  - [ ] Adicionar seção "## Refatoração Completada: Comparação de Preços"
  - [ ] Listar files refatorados e por quê
  - [ ] Atualizar "Arquitetura Alvo" se houve insights novos
  - [ ] Remover de "Problemas Conhecidos" os itens que foram fixados (Blocos A–I)

---

## 4. Definição de Pronto (Definition of Done)

Uma refatoração é considerada **completa e validada** quando:

### Código
- [ ] Todos os problemas identificados inicialmente foram endereçados e resolvidos
- [ ] Nenhuma função tem mais de 2 responsabilidades claras
- [ ] 100% type hints em funções novas e refatoradas
- [ ] Zero imports circulares

### Funcionalidade
- [ ] GET `/comparisons/{id}/summary` retorna resultado idêntico ao antes (exceto mudanças esperadas)
- [ ] Task `compare_prices_task` não quebrou
- [ ] Notificações recebem snapshots válidos e geram eventos corretamente
- [ ] Performance mantém-se (< 10% regressão)

### Documentação
- [ ] market_alert/README.md tem seção de arquitetura de comparação
- [ ] CLAUDE.md atualizado refletindo novo estado
- [ ] Docstrings em todas as funções novas com exemplos

### Compatibilidade
- [ ] Tasks Celery legadas continuam funcionando (wrapper se necessário)
- [ ] Orquestrador continua enfileirando comparações sem erro
- [ ] Dashboard frontend recebe mesma estrutura de dados

---

> Este plano elimina os diversos blocos de problemas identificados na responsabilidade de "Comparação de Preços", fornecendo um caminho claro para restaurar a arquitetura limpa do módulo `market_alert`.
