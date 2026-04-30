""" Classificador de resposta HTTP para decisões de escalonamento.

O classificador recebe o resultado de uma tentativa de aquisição de HTML e
decide qual ação tomar: aceitar como sucesso, escalar para o fallback de
browser (Playwright) ou rejeitar definitivamente. A lógica é puramente funcional —
sem I/O, sem efeitos colaterais — para facilitar testes e auditoria.

Integração esperada:
    1. ``CrawleeRuntime`` obtém HTML via curl_cffi.
    2. O classificador avalia o resultado.
    3. Se action=SCALE, o runtime aciona ``playwright_pool``.
    4. O resultado final é registrado com os campos de telemetria.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog


logger = structlog.get_logger("response_classifier")

# ─────────────────────────────────────────────────────────────────────────────
# Limiares de tamanho de HTML
# ─────────────────────────────────────────────────────────────────────────────

#HTML abaixo deste tamanho é tratado como "vazio" → escala para browser
_HTML_EMPTY_THRESHOLD_BYTES = 1 * 1024       # 1 KB

#Padrões de anti-bot inspecionados pelo classificador e pelo fluxo de fetch
_ANTI_BOT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("suspicious-traffic-frontend", "mercadolivre_challenge"),
    ("challenges.cloudflare.com",   "cloudflare_challenge"),
    ("__cf_chl",                    "cloudflare_challenge"),
    ("__cf_bm",                     "cloudflare_challenge"),
    ("recaptcha/api.js",            "captcha_challenge"),
    ("recaptcha",                   "captcha_challenge"),
    ("_pxcaptcha",                  "perimeterx_challenge"),
)

#Status HTTP que indicam rejeição final (nunca escalar)
_FINAL_REJECT_STATUSES: frozenset[int] = frozenset({404, 410})

#Status HTTP que escalam para browser
_SCALE_TO_LAYER3_STATUSES: frozenset[int] = frozenset({403, 405, 406, *range(500, 600)})

#Status HTTP reservados para estratégia futura; no MVP ainda escalam para browser
_SCALE_TO_LAYER2_STATUSES: frozenset[int] = frozenset({429})

#Padrões de alta confiança que indicam dados estruturados de produto no HTML.
#Deliberadamente restritivos: padrões genéricos ('"price":', '"offers"', "productpage",
#"price-tag", "price_currency_pair") foram removidos pois aparecem em challenge pages
#com scripts de analytics/configuração e causam falso-positivo.
_PRODUCT_SIGNAL_PATTERNS: tuple[str, ...] = (
    "application/ld+json",        # bloco JSON-LD explícito (alta confiança com @type Product/Offer)
    'itemprop="price"',           # microdata de preço (específico de schema.org)
    "ui-pdp-title",               # classe de título de produto do Mercado Livre
    "andes-money-amount",         # componente de preço do Mercado Livre
    "og:price:amount",            # Open Graph — preço do produto (meta tag específica)
    "__preloaded_state__",        # estado JSON pré-carregado do React (Mercado Livre/Shopify)
    '"productId"',                # ID de produto em JSON (e-commerce padrão)
)


# ─────────────────────────────────────────────────────────────────────────────
# Tipos públicos
# ─────────────────────────────────────────────────────────────────────────────

class ClassificationAction(enum.Enum):
    """ Ação decidida pelo classificador após avaliar a resposta."""
    SUCCESS = "success"  # HTML válido, pode seguir para o parser
    SCALE   = "scale"    # Escalar para a próxima estratégia indicada em ``next_layer``
    REJECT  = "reject"   # Rejeição definitiva, sem nova tentativa


@dataclass(frozen=True)
class ClassificationResult:
    """ Resultado imutável da classificação de uma resposta HTTP.

    Attributes:
        action: O que o pipeline deve fazer a seguir.
        next_layer: Estratégia de destino quando ``action=SCALE`` (2 ou 3 por compatibilidade); ``None`` nos demais casos.
        reason: Código legível por humanos que explica a decisão (ex: ``"html_empty"``).
        telemetry: Campos extras prontos para ser adicionados ao log estruturado.
    """
    action: ClassificationAction
    next_layer: int | None
    reason: str
    telemetry: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Funções auxiliares públicas
# ─────────────────────────────────────────────────────────────────────────────

def has_product_signals(html: str) -> bool:
    """ Verifica se o HTML contém sinais de dados estruturados de produto.

    Usado para distinguir páginas de challenge puro (sem conteúdo) de páginas
    que têm anti-bot overlay mas ainda expõem JSON-LD ou microdata de produto.
    Registra em debug se sinais foram encontrados ou não.
    """
    html_lower = html.lower()
    found_patterns = []
    
    for pattern in _PRODUCT_SIGNAL_PATTERNS:
        if pattern.lower() in html_lower:
            found_patterns.append(pattern)
    
    has_signals = bool(found_patterns)
    
    #Log detalhado para debug e diagnóstico
    if found_patterns:
        logger.debug(
            "product_signals_found",
            patterns=found_patterns,
            html_size=len(html),
        )
    else:
        #Log sem sinal mostra padrões esperados e preview do HTML
        logger.debug(
            "product_signals_not_found",
            expected_patterns=list(_PRODUCT_SIGNAL_PATTERNS)[:4],
            html_size=len(html),
            html_preview=html_lower[:300] if len(html) > 0 else "",
        )
    
    return has_signals


def count_product_signals(html: str) -> int:
    """Retorna quantos padrões distintos de produto foram encontrados no HTML."""
    html_lower = html.lower()
    return sum(1 for p in _PRODUCT_SIGNAL_PATTERNS if p.lower() in html_lower)


def detect_anti_bot_pattern(html: str) -> str | None:
    """ Verifica se o HTML contém padrões conhecidos de proteção anti-bot.

    Args:
        html: Conteúdo HTML a ser inspecionado.

    Returns:
        Nome do padrão detectado (ex: ``"cloudflare_challenge"``) ou ``None``
        se nenhum padrão for encontrado.
    """
    html_lower = html.lower()
    for pattern, pattern_type in _ANTI_BOT_PATTERNS:
        if pattern.lower() in html_lower:
            logger.debug(
                "anti_bot_pattern_detected",
                pattern=pattern,
                pattern_type=pattern_type,
            )
            return pattern_type
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Classificador principal
# ─────────────────────────────────────────────────────────────────────────────

class ResponseClassifier:
    """ Avalia respostas HTTP e decide a próxima ação do pipeline.

    O classificador é stateless: pode ser instanciado uma vez e reutilizado
    concorrentemente sem problemas de estado compartilhado.

    Tabela de decisão implementada:

    | HTTP Status   | HTML           | Erro             | Ação    | Next Layer |
    |---------------|----------------|------------------|---------|------------|
    | 200-299       | Normal (≥1KB)  | None             | SUCCESS | —          |
    | 200-299       | Vazio (<1KB)   | None             | SCALE   | 3          |
    | 200-299       | Anti-bot page  | None             | SCALE   | 3          |
    | 429           | Qualquer       | Qualquer         | SCALE   | 3*         |
    | 403, 405, 406 | Qualquer       | Qualquer         | SCALE   | 3          |
    | 404, 410      | Qualquer       | Qualquer         | REJECT  | —          |
    | 500-599       | Qualquer       | Qualquer         | SCALE   | 3          |
    | —             | —              | Timeout          | SCALE   | 3          |
    | —             | —              | Connection error | SCALE   | 3          |
    """

    def classify(
        self,
        *,
        http_status: int | None,
        html: str | None,
        error: Exception | None,
    ) -> ClassificationResult:
        """ Classifica o resultado de uma tentativa de aquisição de HTML.

        Args:
            http_status: Código HTTP da resposta; ``None`` se houve erro de rede.
            html: Conteúdo HTML recebido; ``None`` ou string vazia se indisponível.
            error: Exceção levantada durante o fetch; ``None`` em caso de sucesso.

        Returns:
            ``ClassificationResult`` descrevendo a ação recomendada.
        """
        # ── Erros de rede/transporte (sem status HTTP) ────────────────────
        if error is not None and http_status is None:
            return self._classify_transport_error(error)

        # ── Erros de status HTTP ──────────────────────────────────────────
        if http_status is not None and http_status >= 400:
            return self._classify_http_error(http_status)

        # ── Resposta 200-299 — avaliar qualidade do HTML ──────────────────
        return self._classify_successful_response(html)

    # ── Handlers internos ────────────────────────────────────────────────

    def _classify_transport_error(self, error: Exception) -> ClassificationResult:
        """ Mapeia erros de transporte para ação de escalonamento."""
        if isinstance(error, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout)):
            return ClassificationResult(
                action=ClassificationAction.SCALE,
                next_layer=3,
                reason="timeout",
                telemetry={"error_type": type(error).__name__},
            )

        if isinstance(error, (httpx.ConnectError, httpx.RemoteProtocolError)):
            return ClassificationResult(
                action=ClassificationAction.SCALE,
                next_layer=3,
                reason="connection_error",
                telemetry={"error_type": type(error).__name__},
            )

        #Qualquer outro erro de rede → escala por precaução
        return ClassificationResult(
            action=ClassificationAction.SCALE,
            next_layer=3,
            reason="network_error",
            telemetry={"error_type": type(error).__name__},
        )

    def _classify_http_error(self, http_status: int) -> ClassificationResult:
        """ Mapeia status HTTP de erro para ação de escalonamento ou rejeição."""
        if http_status in _FINAL_REJECT_STATUSES:
            return ClassificationResult(
                action=ClassificationAction.REJECT,
                next_layer=None,
                reason="not_found",
                telemetry={"http_status": http_status},
            )

        if http_status in _SCALE_TO_LAYER2_STATUSES:
            #Estratégia intermediária com proxy não implementada no MVP — escala para browser
            return ClassificationResult(
                action=ClassificationAction.SCALE,
                next_layer=3,
                reason="rate_limited",
                telemetry={"http_status": http_status, "layer2_deferred": True},
            )

        if http_status in _SCALE_TO_LAYER3_STATUSES:
            return ClassificationResult(
                action=ClassificationAction.SCALE,
                next_layer=3,
                reason="access_denied" if http_status in {403, 405, 406} else "server_error",
                telemetry={"http_status": http_status},
            )

        #Outros 4xx não mapeados → rejeição defensiva
        return ClassificationResult(
            action=ClassificationAction.REJECT,
            next_layer=None,
            reason="client_error",
            telemetry={"http_status": http_status},
        )

    def _classify_successful_response(self, html: str | None) -> ClassificationResult:
        """ Avalia qualidade do HTML em respostas 2xx."""
        if not html or len(html.encode("utf-8", errors="replace")) < _HTML_EMPTY_THRESHOLD_BYTES:
            return ClassificationResult(
                action=ClassificationAction.SCALE,
                next_layer=3,
                reason="html_empty",
                telemetry={"html_size_bytes": len(html.encode("utf-8", errors="replace")) if html else 0},
            )

        anti_bot = detect_anti_bot_pattern(html)
        if anti_bot is not None:
            if has_product_signals(html):
                #Anti-bot overlay presente, mas HTML contém sinais de produto (JSON-LD/microdata).
                #Tratar como sucesso degradado: parsers têm chance real de extrair dados úteis.
                return ClassificationResult(
                    action=ClassificationAction.SUCCESS,
                    next_layer=None,
                    reason="anti_bot_degraded",
                    telemetry={"anti_bot_pattern": anti_bot},
                )
            return ClassificationResult(
                action=ClassificationAction.SCALE,
                next_layer=3,
                reason="anti_bot_page",
                telemetry={"anti_bot_pattern": anti_bot},
            )

        #HTML 2xx de tamanho adequado, sem anti-bot, mas sem sinais de produto.
        #Provavelmente shell JS (SPA sem SSR) — escalar para browser que renderiza o DOM real.
        if not has_product_signals(html):
            return ClassificationResult(
                action=ClassificationAction.SCALE,
                next_layer=3,
                reason="html_without_product_signals",
                telemetry={"html_size_bytes": len(html.encode("utf-8", errors="replace"))},
            )

        return ClassificationResult(
            action=ClassificationAction.SUCCESS,
            next_layer=None,
            reason="html_valid",
            telemetry={"html_size_bytes": len(html.encode("utf-8", errors="replace"))},
        )


__all__ = [
    "ClassificationAction",
    "ClassificationResult",
    "ResponseClassifier",
    "detect_anti_bot_pattern",
    "has_product_signals",
    "count_product_signals",
]
