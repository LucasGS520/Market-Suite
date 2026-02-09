""" Testes das heurísticas de inferência de disponibilidade """

from __future__ import annotations

from market_scraper.services.availability_inference import (
    detect_availability,
    infer_availability_from_http_status,
)


def test_infer_availability_from_http_status_404() -> None:
    """ Retorna indisponível quando o status HTTP indica remoção """
    resultado = infer_availability_from_http_status(404, "exemplo.com")

    assert resultado.availability is False
    assert resultado.last_status == "removed"
    assert resultado.confidence == "high"


def test_detect_availability_por_metadata() -> None:
    """ Usa metadata do HTML para inferir indisponibilidade """
    html = "<meta property='og:availability' content='out of stock' />"

    disponibilidade, status = detect_availability(
        html,
        status_code=None,
        domain="exemplo.com",
    )

    assert disponibilidade is False
    assert status == "unavailable"


def test_detect_availability_generico() -> None:
    """ Aplica heurística genérica quando não há domínio específico """
    html = "<div>Produto indisponível no momento</div>"

    disponibilidade, status = detect_availability(
        html,
        status_code=None,
        domain="outro.com",
    )

    assert disponibilidade is False
    assert status == "unavailable"