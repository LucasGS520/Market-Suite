""" Testes para o esquema de scraping com suporte a tipos nativos """

from decimal import Decimal

from backend.shared.schemas.shared_schemas_scraper import ErrorResponse, ParserResponse

def test_precisao_dos_precos() -> None:
    dados = ParserResponse(current_price="0.10")
    assert isinstance(dados.current_price, Decimal)
    assert dados.current_price == Decimal("0.10")

def test_campo_marketplace_preenche_source() -> None:
    dados = ParserResponse(current_price="1.00", marketplace="example.com")
    assert dados.source == "example.com"

def test_error_response_aceita_trace_id_opcional() -> None:
    """Confirma que respostas antigas sem trace_id permanecem válidas"""

    erro_sem_trace = ErrorResponse(message="Falha", error_code="any")
    assert erro_sem_trace.trace_id is None

    erro_com_trace = ErrorResponse(message="Falha", error_code="any", trace_id="abc-123")
    assert erro_com_trace.trace_id == "abc-123"
    