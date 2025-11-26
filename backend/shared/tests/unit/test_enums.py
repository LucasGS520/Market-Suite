""" Testes dos enums BlockResult e ScrapingErrorType para verificar seus valores """

from shared.enums import BlockResult, ScrapingErrorType

def test_block_result_values():
    assert BlockResult.OK.value == "ok"
    assert BlockResult.CAPTCHA.value == "captcha"
    assert BlockResult.HTTP_429.value == "http_429"
    assert BlockResult.HTTP_403.value == "http_403"
    assert BlockResult.UNKNOWN.value == "unknown"

def test_scraping_error_type_values():
    assert ScrapingErrorType.http_error.value == "http_error"
    assert ScrapingErrorType.missing_data.value == "missing_data"
    assert ScrapingErrorType.timeout.value == "timeout"
    assert ScrapingErrorType.parsing_error.value == "parsing_error"
