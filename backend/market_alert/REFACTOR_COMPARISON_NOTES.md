# REFACTOR_COMPARISON_NOTES.md — market_alert

> **Documentação de Mapeamento — FASE 1**  
> Preparação completa antes de qualquer mudança no módulo de comparação.

---

## 1. Funções em `services/services_comparison.py` (1120 linhas)

### Funções Públicas (API de Entrada)

| Função | Responsabilidade | I/O | Tipo |
|--------|------------------|-----|------|
| `ensure_user_can_view_monitored` | Valida autorização do usuário para acessar monitorado | `(db, monitored_id, user)` → void/raise | Impura (consulta) |
| `get_paginated_comparisons_for_user` | Monta envelope paginado de comparações com autorização | `(db, monitored_id, user, page, per_page)` → `PaginatedPriceComparisonResponse` | Impura (consulta + autorização) |
| `get_comparison_summary_for_user` | Retorna resumo mais recente com autorização e reconstrução stale | `(db, monitored_id, user)` → `PriceComparisonSummaryResponse` | Impura (consulta + rebuild + persistência) |
| `get_comparison_detail_for_user` | Obtém comparação específica com autorização | `(db, comparison_id, user)` → `PriceComparisonResponse` | Impura (consulta + autorização) |
| `run_price_comparison` | Executa comparação de preços e persiste resultados | `(db, monitored_id, tolerance?)` → `Dict[str, Any]` | Impura (consulta + cálculo + persistência) |
| `summarize_comparison` | Normaliza resumo de comparação (reutilização/recomputação) | `(comparison?, stored_summary?, force_recompute)` → `Dict[str, Any]` | Pura (não faz I/O) |

### Funções de Orquestração (Coordenam Fluxos)

| Função | Responsabilidade | I/O | Tipo |
|--------|------------------|-----|------|
| `rebuild_summary_from_current_state` | Recompõe resumo usando estado atual de monitorado + concorrentes | `(db, monitored, competitors, stored_summary)` → `Dict` | Impura (usa `_filter_competitors_for_comparison` que consulta DB) |
| `persist_rebuilt_summary_if_needed` | Persiste resumo recomposto apenas se houver mudança material | `(db, monitored_id, normalized_summary, stored_summary)` → `Dict` | Impura (persistência condicional) |

### Funções de Persistência (Orquestram CRUD)

| Função | Responsabilidade | I/O | Tipo |
|--------|------------------|-----|------|
| `_persist_comparison_result` | Persiste comparação e cria/atualiza resumo | `(db, monitored, result, total, available)` → `Dict` | Impura (persistência) |

### Funções de Cálculo (Transformação Pura)

| Função | Responsabilidade | I/O | Tipo |
|--------|------------------|-----|------|
| `_build_material_summary_snapshot` | Extrai campos críticos do resumo para comparação de mudança | `(payload)` → `Dict` | Pura |
| `_compute_summary_from_payload` | Calcula estatísticas competitivas a partir de payload cru | `(payload, timestamp, comparison_id, competitors_count)` → `Dict` | Pura |
| `_calculate_competitiveness_status` | Define status competitivo (competitivo/atenção/urgente) | `(monitored_price, reference_price)` → `str?` | Pura |
| `_calculate_percentage_delta` | Calcula variação percentual entre preços | `(monitored_price, reference_price)` → `Decimal?` | Pura |
| `_build_comparison_insights` | Gera texto explicativo sobre competitividade | `(monitored_price, competitors_min, ...)` → `str?` | Pura |
| `_apply_summary_defaults` | Garante campos obrigatórios no resumo | `(payload, timestamp, comparison_id, competitors_count)` → `Dict` | Pura |
| `_coerce_decimal_fields` | Normaliza campos monetários para Decimal | `(summary)` → `Dict` | Pura |
| `_build_recomputed_summary` | Recalcula resumo sem usar agregados antigos | `(comparison, stored_summary, competitors_count)` → `Dict` | Pura |
| `_empty_summary` | Cria estrutura base do resumo | `(competitors_count)` → `Dict` | Pura |

### Funções de Consulta e Filtragem (Impuras)

| Função | Responsabilidade | I/O | Tipo |
|--------|------------------|-----|------|
| `_load_and_filter_competitors` | Carrega concorrentes e aplica filtro de comparação | `(db, monitored_id, monitored)` → `(list[CompetitorProduct], int)` | Impura (consulta DB + filtragem) |
| `_filter_competitors_for_comparison` | Filtra concorrentes elegíveis com fallback de histórico | `(db, competitors)` → `FilteredCompetitorsResult` | Impura (consulta `PriceHistory`) |
| `_resolve_competitor_comparison_price` | Resolve preço para comparação com fallback histórico | `(db, competitor)` → `(Decimal?, str)` | Impura (consulta `PriceHistory`) |
| `_extract_competitors_count` | Obtém contagem de concorrentes dos agregados | `(stored_summary)` → `int` | Pura |
| `_should_refresh_competitors_count` | Indica quando recarregar contagem por desatualização | `(db, monitored_id, summary_timestamp)` → `bool` | Impura (consulta criação de concorrentes) |

### Funções Auxiliares (Regras de Negócio)

| Função | Responsabilidade | I/O | Tipo |
|--------|------------------|-----|------|
| `_deduplicate_competitors` | Remove duplicidades mantendo concorrente mais recente | `(competitors)` → `list[CompetitorProduct]` | Pura |
| `_resolve_monitored_inactive_reason` | Determina motivo de inatividade do monitorado | `(monitored)` → `str?` | Pura |

### Classes Auxiliares

- **`FilteredCompetitorsResult`**: Agrupa concorrentes elegíveis + métricas de filtragem
  - `entries: list[ComparisonCompetitorEntry]`
  - `filtered_reasons: dict[str, int]`
  - `total_competitors: int`

- **`ComparisonCompetitorEntry`**: Concorrente com preço resolvido
  - `competitor: CompetitorProduct`
  - `price: Decimal`
  - `price_source: str` (ex: "current_price", "price_history")

---

## 2. Campos de `PriceHistory` Lidos em Comparação

### Modelo `PriceHistory` (models_price_history.py)

```python
class PriceHistory(Base):
    id: UUID
    monitored_product_id: UUID | None
    competitor_product_id: UUID | None
    price: Decimal  # ← CAMPO LIDO
    currency: str | None
    checked_at: datetime  # ← CAMPO USADO PARA ORDENAÇÃO
    created_at: datetime  # ← FALLBACK PARA ORDENAÇÃO
```

### Onde é lido?

1. **`_resolve_competitor_comparison_price`** (linha 523-527):
   ```python
   latest_price = (
       db.query(PriceHistory.price)
       .filter(PriceHistory.competitor_product_id == competitor.id)
       .order_by(desc(PriceHistory.checked_at), desc(PriceHistory.created_at))
       .limit(1)
       .scalar()
   )
   ```
   - **Usado quando:** `competitor.current_price` está `None`
   - **Retorna:** último preço registrado no histórico
   - **Fallback:** permite comparação mesmo quando scraping falhou na última coleta

2. **`compare_prices_task._fetch_recent_prices`** (linha 300-302):
   ```python
   history = (
       db.query(PriceHistory)
       .filter(PriceHistory.monitored_product_id == monitored_id)
       .order_by(PriceHistory.checked_at.desc())
       .limit(2)
       .all()
   )
   ```
   - **Usado para:** construir payload de notificação com preço anterior/atual
   - **Não afeta cálculo de comparação diretamente**

**Resumo:** `PriceHistory.price` é lido SOMENTE como fallback quando `current_price` é `None`.

---

## 3. Fluxo de Dados — Onde Cada Entidade Entra

### ASCII Diagram — Fluxo Atual

```
┌───────────────────────────────────────────────────────────────────┐
│                    PONTO DE ENTRADA                                │
├───────────────────────────────────────────────────────────────────┤
│  1. compare_prices_task (Celery)                                  │
│     - Disparado por: scraping_task/orchestrator/recompute         │
│     - Argumentos: monitored_id, price_changed?, trace_id?         │
│     - Invoca: run_price_comparison(db, monitored_id)              │
│                                                                     │
│  2. routes_comparisons.py                                         │
│     - GET /comparisons/{monitored_id}/summary                     │
│     - Invoca: get_comparison_summary_for_user(...)                │
└───────────────────────────────────────────────────────────────────┘
                              ↓
┌───────────────────────────────────────────────────────────────────┐
│             ORQUESTRAÇÃO (services_comparison.py)                 │
├───────────────────────────────────────────────────────────────────┤
│  run_price_comparison(db, monitored_id, tolerance?)               │
│    1. Carrega monitorado via CRUD                                 │
│    2. Carrega + filtra concorrentes (_load_and_filter_competitors)│
│       └─> _filter_competitors_for_comparison(db, competitors)     │
│           └─> _resolve_competitor_comparison_price(db, competitor)│
│               └─> QUERY PriceHistory (fallback)                   │
│    3. Verifica inatividade (_resolve_monitored_inactive_reason)   │
│    4. Chama utils/price_comparator.compare_prices(...)            │
│    5. Persiste resultado (_persist_comparison_result)             │
│       └─> create_price_comparison (CRUD)                          │
│       └─> upsert_price_comparison_summary (CRUD)                  │
└───────────────────────────────────────────────────────────────────┘
                              ↓
┌───────────────────────────────────────────────────────────────────┐
│          CÁLCULO PURO (utils/price_comparator.py)                 │
├───────────────────────────────────────────────────────────────────┤
│  compare_prices(monitored, competitors, tolerance)                │
│    - Filtra concorrentes disponíveis com preço válido             │
│    - Calcula: min, max, média, discrepâncias                      │
│    - Retorna: Dict com monitored_price, discrepancies, lowest...  │
└───────────────────────────────────────────────────────────────────┘
                              ↓
┌───────────────────────────────────────────────────────────────────┐
│        TRANSFORMAÇÃO + PERSISTÊNCIA (services_comparison.py)      │
├───────────────────────────────────────────────────────────────────┤
│  _persist_comparison_result(db, monitored, result, total, ...)    │
│    1. Cria PriceComparison (CRUD)                                 │
│    2. Calcula summary via _compute_summary_from_payload(...)      │
│       - Adiciona: position_rank, potential_adjustment, status     │
│    3. Persiste PriceComparisonSummary (CRUD upsert)               │
└───────────────────────────────────────────────────────────────────┘
                              ↓
┌───────────────────────────────────────────────────────────────────┐
│                  CONSUMIDORES DO RESULTADO                         │
├───────────────────────────────────────────────────────────────────┤
│  1. compare_prices_task → notifications/evaluator.py              │
│     - Usa summary["price_current"], summary["summary"]            │
│                                                                     │
│  2. routes_comparisons.py → Frontend                              │
│     - Retorna PriceComparisonSummaryResponse                      │
│                                                                     │
│  3. services_monitored.py → list_monitored_products               │
│     - Usa rebuild_summary_from_current_state para refresh stale   │
└───────────────────────────────────────────────────────────────────┘
```

---

## 4. Campos Críticos do Snapshot (Material Summary Snapshot)

### Campos em `_build_material_summary_snapshot` (linhas 124-148)

```python
critical_fields = (
    "comparison_id",           # UUID da comparação associada
    "monitored_price",         # Preço do produto monitorado
    "competitors_count",       # Total de concorrentes cadastrados
    "competitors_with_price_count",  # Concorrentes com preço válido
    "competitors_mean",        # Média dos preços dos concorrentes
    "competitors_min",         # Menor preço entre concorrentes
    "competitors_max",         # Maior preço entre concorrentes
    "position_rank",           # Posição do monitorado (1 = mais barato)
    "potential_adjustment",    # Quanto reduzir para igualar o menor
    "ignored_due_to_inactive", # Monitorado sem preço/indisponível
    "competitiveness_status",  # competitivo | atencao | urgente
    "comparison_insights",     # Texto explicativo para frontend
    "discrepancies",           # Lista de discrepâncias por concorrente
    "reason",                  # Motivo de ausência de comparação
)
```

**Campos NÃO incluídos (ignorados propositalmente):**
- `last_comparison_at` — muda a cada request
- `computed_at` — muda a cada recálculo
- Timestamps não afetam a **materialidade** da mudança

---

## 5. Integração com `tasks/compare_prices_task.py`

### Como a Task Invoca Comparação

```python
# linha 80
result = run_price_comparison(db, UUID(monitored_id))
```

**Retorno esperado de `run_price_comparison`:**
```python
{
    "summary": {
        "comparison_id": str(UUID),
        "monitored_price": Decimal | None,
        "competitors_count": int,
        "competitors_with_price_count": int,
        "competitors_min": Decimal | None,
        "competitors_max": Decimal | None,
        "position_rank": int | None,
        "potential_adjustment": Decimal | None,
        "competitiveness_status": str | None,
        "comparison_insights": str | None,
        "discrepancies": [...]
    },
    "comparison_id": str(UUID),
    "monitored_id": str(UUID),
    "user_id": str(UUID),
    "lowest_competitor": {...},
    "highest_competitor": {...}
}
```

**Lógica Duplicada?**
- ❌ **NÃO há duplicação direta** entre task e service
- Task é apenas um **wrapper** que:
  1. Carrega `MonitoredProduct` do banco
  2. Verifica se está pausado (early return)
  3. Chama `run_price_comparison`
  4. Processa resultado para notificações (linha 134-276)
  5. Enfileira `enqueue_notifications_task`

**Problema Identificado:**
- Task executa `_fetch_recent_prices` para construir payload de evento
- **Poderia** estar no service como parte do retorno de `run_price_comparison`

---

## 6. Mapeamento CRUD (`crud/crud_comparison.py`)

### Funções CRUD Utilizadas

| Função CRUD | Invocada Por | Propósito |
|-------------|--------------|-----------|
| `create_price_comparison` | `_persist_comparison_result` | Cria registro de comparação bruta |
| `upsert_price_comparison_summary` | `_persist_comparison_result`, `persist_rebuilt_summary_if_needed` | Cria ou atualiza resumo agregado |
| `get_comparison_by_id` | `get_comparison_detail_for_user` | Busca comparação específica por ID |
| `get_latest_summary` | `get_comparison_summary_for_user` | Retorna resumo mais recente do monitorado |
| `paginate_comparisons` | `get_paginated_comparisons_for_user` | Lista comparações paginadas |
| `get_latest_summaries_for_products` | `services_monitored.list_monitored_products` | Busca resumos em lote para lista |
| `get_latest_comparisons_for_products` | (não usado diretamente) | Busca comparações em lote |

### Por que `upsert_price_comparison_summary` existe?

- **Razão:** Comparações múltiplas podem referenciar o mesmo `comparison_id`
- **Idempotência:** Permite refresh de resumo sem duplicar registros
- **Uso:** 
  - Criação inicial: após `run_price_comparison`
  - Atualização: quando `rebuild_summary_from_current_state` detecta mudança material

---

## 7. Schema Pydantic (`schemas/schemas_comparisons.py`)

### `PriceComparisonSummaryResponse`

```python
class PriceComparisonSummaryResponse(BaseModel):
    monitored_product_id: UUID                     # Obrigatório
    comparison_id: Optional[UUID] = None           # Pode ser None quando sem comparação
    last_comparison_at: Optional[datetime] = None  # Timestamp da última comparação
    computed_at: Optional[datetime] = None         # Timestamp do cálculo do resumo
    monitored_price: Optional[Decimal] = None      # Preço do monitorado
    competitors_count: int = 0                     # Total de concorrentes
    competitors_with_price_count: int = 0          # Concorrentes elegíveis
    competitors_mean: Optional[Decimal] = None     # Média dos preços
    competitors_min: Optional[Decimal] = None      # Menor preço
    competitors_max: Optional[Decimal] = None      # Maior preço
    position_rank: Optional[int] = None            # Posição no ranking
    potential_adjustment: Optional[Decimal] = None # Ajuste sugerido
    ignored_due_to_inactive: bool = False          # Indica inatividade
    comparison_insights: Optional[str] = None      # Texto explicativo
    competitiveness_status: Optional[CompetitivenessStatus] = None  # Status
    discrepancies: List[Dict[str, Any]] = []       # Lista de concorrentes
    reason: Optional[str] = None                   # Motivo de ausência de dados
```

**Transformação de Tipos:**
- `Decimal` → `float` via `json_encoders={Decimal: float}` (linha 40)
- Garante que frontend receba números JSON válidos

**Campos Opcionais e Por Quê:**
- `comparison_id`: pode não existir comparação ainda
- `monitored_price`: produto pode estar sem preço coletado
- `competitors_min/max/mean`: pode não haver concorrentes com preço
- `position_rank`: só calculado se houver preços válidos
- `competitiveness_status`: só definido se houver referência válida

---

## 8. Rotas (`routes/routes_comparisons.py`)

### Endpoints e Serviços Invocados

| Rota | Método | Serviço Chamado | Autorização |
|------|--------|-----------------|-------------|
| `/comparisons/{monitored_id}` | GET | `get_paginated_comparisons_for_user` | ✅ via `ensure_user_can_view_monitored` |
| `/comparisons/{monitored_id}/summary` | GET | `get_comparison_summary_for_user` | ✅ via `ensure_user_can_view_monitored` |
| `/comparisons/detail/{comparison_id}` | GET | `get_comparison_detail_for_user` | ✅ via `ensure_user_can_view_monitored` |

**Validação de Entrada:**
- `page`: `ge=1` (base 1)
- `per_page`: `ge=1, le=100`

**Não há:**
- ❌ Endpoints de criação manual
- ❌ Endpoints de deleção
- ❌ Endpoints de atualização
- Comparações são criadas **apenas** via task Celery

---

## 9. Consumidores de Comparação

### `notifications/evaluator.py`

**Campos do snapshot esperados:**
```python
current_snapshot = {
    "price": float | None,                  # Preço atual do monitorado
    "availability": bool | None,            # Disponibilidade atual
    "summary": Dict[str, Any],              # ← RESUMO COMPLETO DA COMPARAÇÃO
    "price_delta_percent": float | None,    # Variação percentual
}
```

**Uso do `summary`:**
- Incluído no payload de notificação
- Usado no template de email/SMS para mostrar insights
- **Não extrai campos específicos** — repassa o dict completo

### `services/services_monitored.py`

**Função:** `_refresh_stale_summary_if_needed`

**Fluxo:**
1. Verifica se contagem de concorrentes está desatualizada
2. Se sim, chama `rebuild_summary_from_current_state`
3. Persiste via `persist_rebuilt_summary_if_needed`
4. Retorna resumo normalizado

**Por que existe?**
- Endpoint `/monitored` pode ser chamado MUITO antes de uma nova comparação rodar
- Garante que contadores reflitam o estado atual do cadastro

### `services/services_products.py`

**Função:** `build_monitored_response`

**Uso de `summarize_comparison`:**
```python
normalized_summary = summarize_comparison(
    None,  # comparison não fornecida
    summary,  # ORM PriceComparisonSummary
)
```

**Por que?**
- Normaliza ORM para dict antes de construir `PriceComparisonSummaryResponse`
- Garante formato consistente independente da origem

---

## 10. Identificação de Funções Puras vs Impuras

### Funções Puras (Sem I/O, Deterministicas)

✅ Podem ser extraídas para módulo separado de cálculo:
- `_build_material_summary_snapshot`
- `_compute_summary_from_payload`
- `_calculate_competitiveness_status`
- `_calculate_percentage_delta`
- `_build_comparison_insights`
- `_apply_summary_defaults`
- `_coerce_decimal_fields`
- `_build_recomputed_summary`
- `_empty_summary`
- `_deduplicate_competitors`
- `_resolve_monitored_inactive_reason`
- `_extract_competitors_count` (lê de dict, não de DB)
- `summarize_comparison` (lê de objetos já carregados)

### Funções Impuras (Fazem I/O)

❌ Precisam permanecer no service com acesso a DB:
- `ensure_user_can_view_monitored` (consulta)
- `get_paginated_comparisons_for_user` (consulta + autorização)
- `get_comparison_summary_for_user` (consulta + rebuild + persist)
- `get_comparison_detail_for_user` (consulta + autorização)
- `run_price_comparison` (consulta + persist)
- `rebuild_summary_from_current_state` (consulta PriceHistory indiretamente)
- `persist_rebuilt_summary_if_needed` (persist)
- `_persist_comparison_result` (persist)
- `_load_and_filter_competitors` (consulta)
- `_filter_competitors_for_comparison` (consulta PriceHistory)
- `_resolve_competitor_comparison_price` (consulta PriceHistory)
- `_should_refresh_competitors_count` (consulta)

---

## 11. Problemas Identificados

### 🔴 Violações de Responsabilidade Única

1. **`get_comparison_summary_for_user`** faz 4 coisas:
   - Autorização
   - Consulta de resumo armazenado
   - Reconstrução do resumo (rebuild)
   - Persistência condicional

2. **`run_price_comparison`** faz 5 coisas:
   - Carregamento de produtos
   - Filtragem de concorrentes
   - Cálculo de comparação (delega)
   - Persistência de comparação
   - Persistência de resumo

3. **`rebuild_summary_from_current_state`** faz 3 coisas:
   - Filtragem de concorrentes (com query DB)
   - Cálculo de discrepâncias
   - Aplicação de defaults

### 🔴 Consulta DB em Função de "Rebuild"

- `rebuild_summary_from_current_state` → `_filter_competitors_for_comparison` → `_resolve_competitor_comparison_price`
- **Problema:** Função que deveria "recompor" a partir de dados em memória faz queries ao DB
- **Consequência:** Difícil testar sem mock de DB

### 🔴 Duplicação de Lógica de Filtragem

- `_filter_competitors_for_comparison` duplica lógica similar ao `compare_prices` em `utils/price_comparator.py`
- Ambos filtram por: `paused`, `status`, `availability`, `missing_price`

### 🔴 Mixing de Camadas

- Service chama CRUD diretamente (`create_price_comparison`, `upsert_price_comparison_summary`)
- Service importa modelo ORM (`PriceHistory`) para fazer query direta
- Correto seria: Service → CRUD → Model

---

## 13. Métricas de Complexidade

| Métrica | Valor Atual | Objetivo Pós-Refactor |
|---------|-------------|------------------------|
| Linhas em `services_comparison.py` | 1120 | < 400 (serviço) + < 300 (calculator) |
| Funções públicas | 6 | 4 (remover rebuild público) |
| Funções privadas | 22 | < 10 no service |
| Consultas DB diretas | 3 | 0 (tudo via CRUD) |
| Imports de modelos | 2 (`PriceHistory`, `CompetitorProduct`) | 0 em calculator, 1 em service |
| Nível de aninhamento (max) | 4 | 3 |

---

**Documento criado em:** 2026-02-24  
**Última atualização:** 2026-02-24  
**Responsável:** Agente Copilot (FASE 1 — Mapeamento)
