""" Catálogo semântico de outcomes e reasons de coleta.

Fonte única de verdade para todos os módulos que produzem ou consomem
resultados de coleta: coletor (collector_product_task, collector_result),
orquestrador (status_activity, workflow) e comparação (price_comparator,
services_comparison).

Regra de ouro: nenhum módulo crítico deve usar strings literais para
outcome/reason — apenas constantes deste catálogo.

---

## Semântica de Outcomes

| Outcome             | Significado                                                             |
|---------------------|-------------------------------------------------------------------------|
| success             | Coleta com persistência válida e dados mínimos obrigatórios.            |
| not_modified        | Origem íntegra validada; nenhuma mudança material detectada (304/ETag). |
| error               | Falha técnica tipada: transitória, estrutural ou de infra.              |
| no_result           | Ausência legítima de dado após captura e parse íntegros.                |

## Semântica de Neutralidade Operacional (via reason)

| Reason                  | Significado                                                         |
|-------------------------|---------------------------------------------------------------------|
| lock_skipped            | Lock não adquirido — outro worker está coletando o produto.         |
| ignored_due_to_inactive | Produto inativo/pausado — coleta descartada intencionalmente.       |

Nota: razões neutras resultam em outcome=no_result com reason tipado.
O workflow interpreta esses reasons como "completed sem erro" (WaitingTimer).

---

## Classes de Erro

| Classe       | Descrição                                          | Retryable |
|--------------|----------------------------------------------------|-----------|
| transient    | Falha temporária de infra/rede; tende a se corrigir| Sim       |
| structural   | Estrutura de página inválida; requer ação humana   | Condicional|
| domain_empty | Resultado vazio legítimo (produto sem preço etc.)  | Não       |
| neutral      | Operacional — sem impacto em qualidade de dados    | Não       |

---

## Decisão do Workflow

| Outcome     | Reason                  | Decisão         |
|-------------|-------------------------|-----------------|
| success     | —                       | WaitingTimer    |
| not_modified| —                       | WaitingTimer    |
| error       | (transient)             | Backoff         |
| error       | (structural)            | Backoff         |
| no_result   | (domain_empty)          | Backoff         |
| no_result   | lock_skipped            | WaitingTimer    |
| no_result   | ignored_due_to_inactive | WaitingTimer    |
| no_result   | scraping_suspended      | WaitingTimer    |
| no_result   | missing_target          | WaitingTimer    |
| no_result   | paused                  | WaitingTimer    |

---

## Pontos em Aberto (decisão pendente)

- Retry de erros estruturais de página: selector_missing e
  unexpected_content_type têm retryable=False por padrão; revisar se
  política de domínio/host deve sobrescrever.
- source_integrity: derivado internamente por regra no coletor (v1);
  campo explícito em versão futura do payload.
- Granularidade de reason para dashboards: dom_not_ready e selector_missing
  separados (padrão atual); agrupar em parse_structure_error se necessário.
"""

from __future__ import annotations

CATALOG_VERSION = 1

# ─────────────────────────── Outcomes ─────────────────────────────────────────

OUTCOME_SUCCESS = "success"
OUTCOME_NOT_MODIFIED = "not_modified"
OUTCOME_ERROR = "error"
OUTCOME_NO_RESULT = "no_result"

VALID_OUTCOMES: frozenset[str] = frozenset({
    OUTCOME_SUCCESS,
    OUTCOME_NOT_MODIFIED,
    OUTCOME_ERROR,
    OUTCOME_NO_RESULT,
})

# Outcomes que indicam término bem-sucedido (sem erro de negócio)
SUCCESSFUL_OUTCOMES: frozenset[str] = frozenset({OUTCOME_SUCCESS, OUTCOME_NOT_MODIFIED})

# ─────────────────────────── Reasons — Erro ───────────────────────────────────

# Transitórios (infraestrutura/rede — tendem a se corrigir sozinhos)
REASON_HTTP_429 = "http_429"
REASON_CHALLENGE_DETECTED = "challenge_detected"
REASON_NAVIGATION_TIMEOUT = "navigation_timeout"
REASON_HTTP_ERROR = "http_error"
REASON_SCRAPER_UNAVAILABLE = "scraper_unavailable"
REASON_SCRAPER_CLIENT_ERROR = "scraper_client_error"
REASON_SCRAPER_ERROR = "scraper_error"
REASON_UNEXPECTED_ERROR = "unexpected_error"
REASON_DB_ERROR = "db_error"
REASON_TASK_UNHANDLED = "task_unhandled_exception"

# Estruturais (falha de estrutura de página — requer atenção humana ou mudança de parser)
REASON_DOM_NOT_READY = "dom_not_ready"
REASON_SELECTOR_MISSING = "selector_missing"
REASON_PARSE_PRICE_FAILED = "parse_price_failed"
REASON_UNEXPECTED_CONTENT_TYPE = "unexpected_content_type"
REASON_INVALID_URL = "invalid_url"
REASON_BLOCKED_HOST = "blocked_host"
REASON_ROBOTS_DISALLOWED = "robots_disallowed"
REASON_INVALID_PAYLOAD = "invalid_payload"

# ─────────────────────────── Reasons — Domínio Vazio ──────────────────────────

# Ausência legítima de dado após captura e parse íntegros
REASON_NO_PRICE = "no_price"
REASON_PRODUCT_UNAVAILABLE = "product_unavailable"
REASON_PARSE_EMPTY = "parse_empty"

# ─────────────────────────── Reasons — Neutros ────────────────────────────────

# Operacionais — não representam falha de produto, workflow retorna a WaitingTimer
REASON_LOCK_SKIPPED = "lock_skipped"
REASON_IGNORED_INACTIVE = "ignored_due_to_inactive"
REASON_SCRAPING_SUSPENDED = "scraping_suspended"
REASON_MISSING_TARGET = "missing_target"
REASON_PAUSED = "paused"

# Conjunto de todos os reasons neutros — sem backoff, sem erro de negócio
NEUTRAL_REASONS: frozenset[str] = frozenset({
    REASON_LOCK_SKIPPED,
    REASON_IGNORED_INACTIVE,
    REASON_SCRAPING_SUSPENDED,
    REASON_MISSING_TARGET,
    REASON_PAUSED,
})

# ─────────────────────────── Classes de Erro ──────────────────────────────────

ERROR_CLASS_TRANSIENT = "transient"
ERROR_CLASS_STRUCTURAL = "structural"
ERROR_CLASS_DOMAIN_EMPTY = "domain_empty"
ERROR_CLASS_NEUTRAL = "neutral"

# ─────────────────────────── Decisões do Workflow ─────────────────────────────

WORKFLOW_WAITING_TIMER = "waiting_timer"
WORKFLOW_BACKOFF = "backoff"

# ─────────────────────────── Tabelas de Classificação ─────────────────────────

# Mapeamento reason → classe de erro
REASON_ERROR_CLASS: dict[str, str] = {
    # Transitórios
    REASON_HTTP_429: ERROR_CLASS_TRANSIENT,
    REASON_CHALLENGE_DETECTED: ERROR_CLASS_TRANSIENT,
    REASON_NAVIGATION_TIMEOUT: ERROR_CLASS_TRANSIENT,
    REASON_HTTP_ERROR: ERROR_CLASS_TRANSIENT,
    REASON_SCRAPER_UNAVAILABLE: ERROR_CLASS_TRANSIENT,
    REASON_SCRAPER_CLIENT_ERROR: ERROR_CLASS_TRANSIENT,
    REASON_SCRAPER_ERROR: ERROR_CLASS_TRANSIENT,
    REASON_UNEXPECTED_ERROR: ERROR_CLASS_TRANSIENT,
    REASON_DB_ERROR: ERROR_CLASS_TRANSIENT,
    REASON_TASK_UNHANDLED: ERROR_CLASS_TRANSIENT,
    # Estruturais
    REASON_DOM_NOT_READY: ERROR_CLASS_STRUCTURAL,
    REASON_SELECTOR_MISSING: ERROR_CLASS_STRUCTURAL,
    REASON_PARSE_PRICE_FAILED: ERROR_CLASS_STRUCTURAL,
    REASON_UNEXPECTED_CONTENT_TYPE: ERROR_CLASS_STRUCTURAL,
    REASON_INVALID_URL: ERROR_CLASS_STRUCTURAL,
    REASON_BLOCKED_HOST: ERROR_CLASS_STRUCTURAL,
    REASON_ROBOTS_DISALLOWED: ERROR_CLASS_STRUCTURAL,
    REASON_INVALID_PAYLOAD: ERROR_CLASS_STRUCTURAL,
    # Domínio vazio
    REASON_NO_PRICE: ERROR_CLASS_DOMAIN_EMPTY,
    REASON_PRODUCT_UNAVAILABLE: ERROR_CLASS_DOMAIN_EMPTY,
    REASON_PARSE_EMPTY: ERROR_CLASS_DOMAIN_EMPTY,
    # Neutros
    REASON_LOCK_SKIPPED: ERROR_CLASS_NEUTRAL,
    REASON_IGNORED_INACTIVE: ERROR_CLASS_NEUTRAL,
    REASON_SCRAPING_SUSPENDED: ERROR_CLASS_NEUTRAL,
    REASON_MISSING_TARGET: ERROR_CLASS_NEUTRAL,
    REASON_PAUSED: ERROR_CLASS_NEUTRAL,
}

# Mapeamento reason → retryabilidade
# Pontos em aberto: selector_missing e unexpected_content_type podem ser
# retryable dependendo da política de domínio/host — default=False.
REASON_IS_RETRYABLE: dict[str, bool] = {
    REASON_HTTP_429: True,
    REASON_CHALLENGE_DETECTED: True,
    REASON_NAVIGATION_TIMEOUT: True,
    REASON_DOM_NOT_READY: True,
    REASON_SELECTOR_MISSING: False,
    REASON_PARSE_PRICE_FAILED: True,
    REASON_UNEXPECTED_CONTENT_TYPE: False,
    REASON_HTTP_ERROR: True,
    REASON_SCRAPER_UNAVAILABLE: True,
    REASON_INVALID_URL: False,
    REASON_BLOCKED_HOST: False,
    REASON_ROBOTS_DISALLOWED: False,
    REASON_INVALID_PAYLOAD: False,
    REASON_SCRAPER_CLIENT_ERROR: True,
    REASON_SCRAPER_ERROR: True,
    REASON_UNEXPECTED_ERROR: True,
    REASON_DB_ERROR: True,
    REASON_TASK_UNHANDLED: True,
    REASON_NO_PRICE: False,
    REASON_PRODUCT_UNAVAILABLE: False,
    REASON_PARSE_EMPTY: False,
    REASON_LOCK_SKIPPED: False,
    REASON_IGNORED_INACTIVE: False,
    REASON_SCRAPING_SUSPENDED: False,
    REASON_MISSING_TARGET: False,
    REASON_PAUSED: False,
}

# ─────────────────────────── Helpers ──────────────────────────────────────────

def get_error_class(reason: str | None) -> str:
    """ Retorna a classe de erro para um reason, ou 'transient' se desconhecido. """
    if reason is None:
        return ERROR_CLASS_TRANSIENT
    return REASON_ERROR_CLASS.get(reason, ERROR_CLASS_TRANSIENT)


def is_retryable(reason: str | None) -> bool:
    """ Retorna se o reason é retryável; assume True para reasons desconhecidos. """
    if reason is None:
        return True
    return REASON_IS_RETRYABLE.get(reason, True)


def has_source_integrity(outcome: str | None, reason: str | None) -> bool:
    """ Indica se houve origem íntegra suficiente para confiar no resultado.

    Regras atuais:
    - `success` e `not_modified` sempre carregam integridade de origem.
    - `no_result` só é íntegro quando representa vazio legítimo de domínio.
    - falhas técnicas, reasons neutros e values desconhecidos não são íntegros.
    """
    if outcome in SUCCESSFUL_OUTCOMES:
        return True
    if outcome == OUTCOME_NO_RESULT:
        return get_error_class(reason) == ERROR_CLASS_DOMAIN_EMPTY
    return False


def get_workflow_decision(outcome: str, reason: str | None) -> str:
    """ Retorna a decisão do workflow com base no outcome e reason.

    Regras:
    - success / not_modified → WaitingTimer (sem erro)
    - no_result com reason neutro → WaitingTimer (operacional, sem erro de produto)
    - no_result com reason de domínio_vazio ou ausente → Backoff
    - error (qualquer reason) → Backoff
    - outcome desconhecido → Backoff (conservador)
    """
    if outcome in SUCCESSFUL_OUTCOMES:
        return WORKFLOW_WAITING_TIMER
    if outcome == OUTCOME_NO_RESULT and reason in NEUTRAL_REASONS:
        return WORKFLOW_WAITING_TIMER
    return WORKFLOW_BACKOFF


def is_neutral_outcome(outcome: str, reason: str | None) -> bool:
    """ Verdadeiro quando outcome/reason não representa falha de produto. """
    return get_workflow_decision(outcome, reason) == WORKFLOW_WAITING_TIMER


__all__ = [
    "CATALOG_VERSION",
    # Outcomes
    "OUTCOME_SUCCESS",
    "OUTCOME_NOT_MODIFIED",
    "OUTCOME_ERROR",
    "OUTCOME_NO_RESULT",
    "VALID_OUTCOMES",
    "SUCCESSFUL_OUTCOMES",
    # Reasons — erro transitório
    "REASON_HTTP_429",
    "REASON_CHALLENGE_DETECTED",
    "REASON_NAVIGATION_TIMEOUT",
    "REASON_HTTP_ERROR",
    "REASON_SCRAPER_UNAVAILABLE",
    "REASON_SCRAPER_CLIENT_ERROR",
    "REASON_SCRAPER_ERROR",
    "REASON_UNEXPECTED_ERROR",
    "REASON_DB_ERROR",
    "REASON_TASK_UNHANDLED",
    # Reasons — erro estrutural
    "REASON_DOM_NOT_READY",
    "REASON_SELECTOR_MISSING",
    "REASON_PARSE_PRICE_FAILED",
    "REASON_UNEXPECTED_CONTENT_TYPE",
    "REASON_INVALID_URL",
    "REASON_BLOCKED_HOST",
    "REASON_ROBOTS_DISALLOWED",
    "REASON_INVALID_PAYLOAD",
    # Reasons — domínio vazio
    "REASON_NO_PRICE",
    "REASON_PRODUCT_UNAVAILABLE",
    "REASON_PARSE_EMPTY",
    # Reasons — neutros
    "REASON_LOCK_SKIPPED",
    "REASON_IGNORED_INACTIVE",
    "REASON_SCRAPING_SUSPENDED",
    "REASON_MISSING_TARGET",
    "REASON_PAUSED",
    "NEUTRAL_REASONS",
    # Classes de erro
    "ERROR_CLASS_TRANSIENT",
    "ERROR_CLASS_STRUCTURAL",
    "ERROR_CLASS_DOMAIN_EMPTY",
    "ERROR_CLASS_NEUTRAL",
    # Decisões do workflow
    "WORKFLOW_WAITING_TIMER",
    "WORKFLOW_BACKOFF",
    # Tabelas
    "REASON_ERROR_CLASS",
    "REASON_IS_RETRYABLE",
    # Helpers
    "get_error_class",
    "is_retryable",
    "has_source_integrity",
    "get_workflow_decision",
    "is_neutral_outcome",
]
