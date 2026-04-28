""" Cadeia determinística de extração de dados de produto.

Implementa estritamente a ordem canônica final: extruct → parsel → bs4+lxml.

A cadeia para na primeira extração válida e mantém evidências de todas
as tentativas, independentemente de sucesso ou falha. Aceita dados brutos
e retorna ParseResult tipado.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Mapping

import structlog

from market_scraper.domain.dtos import ParseAttempt, ParseResult
from market_scraper.extraction.parsers import (
    parse_with_beautifulsoup,
    parse_with_extruct,
    parse_with_parsel,
)
from market_scraper.services.availability_inference import detect_availability
from market_scraper.utils.http_utils import extract_domain
from market_scraper.utils.validator import DataQualityValidator


logger = structlog.get_logger("extraction_chain")

_validator = DataQualityValidator()


class ExtractionChain:
    """ Cadeia fixa e imutável de extração: extruct → parsel → beautifulsoup.

    Cada passo tenta um parser independentemente dos anteriores — falha de
    um parser não interrompe a cadeia. A cadeia encerra no primeiro payload
    que satisfaça os critérios mínimos de qualidade (nome + preço, ou
    indisponibilidade explícita).
    """

    def run(
        self,
        html: str,
        url: str,
        source: str | None,
        *,
        http_status: int | None = None,
    ) -> ParseResult:
        """ Executa a cadeia de extração e retorna ParseResult com evidências.

        Args:
            html: HTML bruto da página de produto.
            url: URL canônica do produto (já normalizada).
            source: Domínio da página (ex.: "mercadolivre.com.br").
            http_status: Status HTTP recebido na coleta (influencia inferência de disponibilidade).

        Returns:
            ParseResult com payload (se extraído) e lista de tentativas para telemetria.
        """
        t_start = time.perf_counter()
        attempts: list[ParseAttempt] = []
        domain = source or extract_domain(url) or ""

        def _elapsed() -> float:
            return (time.perf_counter() - t_start) * 1000

        #Passo 1: extruct — JSON-LD e dados estruturados (maior fidelidade)
        attempt, payload = self._try_parser(
            "extruct", parse_with_extruct, html, url, source, http_status
        )
        attempts.append(attempt)
        if payload is not None:
            return ParseResult(payload=payload, attempts=tuple(attempts), duration_ms=_elapsed())

        #Passo 2: parsel — XPath/CSS genérico (fallback estruturado)
        attempt, payload = self._try_parser(
            "parsel", parse_with_parsel, html, url, source, http_status
        )
        attempts.append(attempt)
        if payload is not None:
            return ParseResult(payload=payload, attempts=tuple(attempts), duration_ms=_elapsed())

        #Passo 3: beautifulsoup — metatags HTML com parser lxml
        attempt, payload = self._try_parser(
            "beautifulsoup", parse_with_beautifulsoup, html, url, source, http_status
        )
        attempts.append(attempt)
        if payload is not None:
            return ParseResult(payload=payload, attempts=tuple(attempts), duration_ms=_elapsed())

        logger.info(
            "extraction_chain_exhausted",
            url=url,
            domain=domain,
            attempts=len(attempts),
        )
        return ParseResult(payload=None, attempts=tuple(attempts), duration_ms=_elapsed())

    def _try_parser(
        self,
        parser_name: str,
        parser: Callable[[str, str], dict[str, Any] | None],
        html: str,
        url: str,
        source: str | None,
        http_status: int | None,
    ) -> tuple[ParseAttempt, dict[str, Any] | None]:
        """ Executa um parser individual e retorna (tentativa, payload_ou_None). """
        t0 = time.perf_counter()
        try:
            raw = parser(html, url)
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.warning(
                "extraction_chain_parser_error",
                parser=parser_name,
                url=url,
                error=str(exc),
            )
            return (
                ParseAttempt(
                    parser_name=parser_name,
                    step_name=parser_name,
                    succeeded=False,
                    reason_code="parser_error",
                    reason_message=str(exc),
                    duration_ms=duration_ms,
                ),
                None,
            )

        if not raw:
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.debug("extraction_chain_no_data", parser=parser_name, url=url)
            return (
                ParseAttempt(
                    parser_name=parser_name,
                    step_name=parser_name,
                    succeeded=False,
                    reason_code="parser_no_data",
                    reason_message="Parser não retornou dados extraíveis",
                    duration_ms=duration_ms,
                ),
                None,
            )

        inferred_availability, inferred_last_status = detect_availability(
            html, status_code=http_status, domain=source
        )

        validated = _validator.validate(
            step_name=parser_name,
            payload=raw,
            url=url,
            source=source or "",
            parser_name=parser_name,
            dump_path=None,
            inferred_availability=inferred_availability,
            inferred_last_status=inferred_last_status,
        )

        if not validated.is_valid:
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.debug(
                "extraction_chain_invalid",
                parser=parser_name,
                reason=validated.reason_code,
                url=url,
            )
            return (
                ParseAttempt(
                    parser_name=parser_name,
                    step_name=parser_name,
                    succeeded=False,
                    reason_code=validated.reason_code,
                    reason_message=validated.reason_message,
                    duration_ms=duration_ms,
                ),
                None,
            )

        if not validated.is_useful:
            duration_ms = (time.perf_counter() - t0) * 1000
            return (
                ParseAttempt(
                    parser_name=parser_name,
                    step_name=parser_name,
                    succeeded=False,
                    reason_code="not_useful",
                    reason_message="Payload válido mas sem critérios mínimos (nome+preço ou indisponibilidade)",
                    duration_ms=duration_ms,
                ),
                None,
            )

        duration_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "extraction_chain_success",
            parser=parser_name,
            url=url,
            domain=source,
        )
        return (
            ParseAttempt(
                parser_name=parser_name,
                step_name=parser_name,
                succeeded=True,
                duration_ms=duration_ms,
            ),
            dict(validated.payload),
        )


__all__ = ["ExtractionChain"]
