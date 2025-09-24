""" Valida utilidades de logging, como a máscara e sanitização de dados sensíveis """

from shared.utils.logging_utils import mask_identifier, sanitize_log_data

def test_mask_identifier_long():
    assert mask_identifier("1234567890") == "1234***7890"


def test_mask_identifier_short_or_empty():
    assert mask_identifier("1234") == "1234"
    assert mask_identifier("") == ""

def test_sanitize_log_data_dict():
    """ Deve substituir valores sensíveis em dicionários aninhados """

    payload = {
        "token": "abc",
        "dados": {"authorization": "Bearer xxx", "nome": "Produto"},
    }

    resultado = sanitize_log_data(payload)

    assert resultado["token"] == "[REDACTED]"
    assert resultado["dados"]["authorization"] == "[REDACTED]"
    assert resultado["dados"]["nome"] == "Produto"

def test_sanitize_log_data_url():
    """ Deve preservar a URL mascarando apenas parâmetros sensíveis """
    url = "https://exemplo.com/item?token=abc&ref=123"
    sanitized = sanitize_log_data(url)

    assert sanitized.startswith("https://exemplo.com/item")
    assert "token=%5BREDACTED%5D" in sanitized
    assert "ref=123" in sanitized
