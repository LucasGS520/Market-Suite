from app.utils.logging_utils import mask_identifier


def test_mask_identifier_long():
    assert mask_identifier("1234567890") == "1234***7890"


def test_mask_identifier_short_or_empty():
    assert mask_identifier("1234") == "1234"
    assert mask_identifier("") == ""
