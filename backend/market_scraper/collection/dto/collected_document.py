""" DTO imutável para o resultado completo de uma operação de coleta. """

from __future__ import annotations

from dataclasses import dataclass, field

from market_scraper.collection.dto.collection_attempt import CollectionAttempt


@dataclass(frozen=True)
class CollectedDocument:
    """ Resultado fechado e tipado de uma operação de coleta de HTML.

    Produzido pelo CrawleeRuntime após todas as tentativas de aquisição
    (HTTP com possível fallback para browser). Entrada para a camada de extração.

    Attributes:
        html: HTML bruto obtido, ou ``None`` em caso de falha total.
        http_status: Status HTTP da tentativa primária, ou ``None`` se exceção.
        headers: Headers HTTP recebidos na tentativa primária.
        layer_used: Camada final que entregou o HTML — ``"http"`` ou ``"browser"``.
        fallback_taken: True se o fallback para browser foi acionado.
        anti_bot_detected: True se algum marcador anti-bot foi detectado.
        anti_bot_pattern: Nome do padrão anti-bot detectado, ou ``None``.
        timestamp: Unix timestamp de início da operação (time.time()).
        duration_ms: Duração total da coleta em milissegundos.
        attempts: Registro imutável de todas as tentativas realizadas.
        final_url: URL final após redirecionamentos; ``None`` se não rastreado (Crawlee preenche na Fase 4).
    """

    html: str | None
    http_status: int | None
    headers: dict[str, str]
    layer_used: str
    fallback_taken: bool
    anti_bot_detected: bool
    anti_bot_pattern: str | None
    timestamp: float
    duration_ms: float
    attempts: tuple[CollectionAttempt, ...] = field(default_factory=tuple)
    error_code: str | None = None
    classification_reason: str | None = None
    anti_bot_bypassed: bool = False
    final_url: str | None = None

    @property
    def is_successful(self) -> bool:
        """ True se HTML foi obtido com conteúdo não vazio. """
        return self.html is not None and len(self.html.strip()) > 0

    @property
    def data_quality(self) -> str:
        """ Indicador canônico de qualidade da aquisição.

        Returns:
            ``"browser_fallback"`` se fallback foi usado,
            ``"degraded_anti_bot"`` se anti-bot detectado sem fallback,
            ``"normal"`` caso contrário.
        """
        if self.fallback_taken:
            return "browser_fallback"
        if self.anti_bot_detected:
            return "degraded_anti_bot"
        return "normal"


__all__ = ["CollectedDocument"]
