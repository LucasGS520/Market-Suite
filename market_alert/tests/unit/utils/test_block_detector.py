import requests

from app.utils.block_detector import detect_block, BlockResult

def _fake_response(status=200, text="<html></html>"):
    r = requests.Response()
    r.status_code = status
    r._content = text.encode("utf-8")
    r.encoding = "utf-8"
    r.headers = {"Content-Type": "text/html"}
    return r

def test_detect_block_ok():
    """ Respostas normais não devem indicar bloqueio """
    resp = _fake_response(200, "ok")
    assert detect_block(resp) is BlockResult.OK

def test_detect_block_captcha():
    """ Detecta bloqueio por CAPTCHA no HTML """
    resp = _fake_response(200, "Please complete the CAPTCHA")
    assert detect_block(resp) is BlockResult.CAPTCHA

def test_detect_block_http_429():
    """ HTTP 429 deve ser classificado como bloqueio """
    resp = _fake_response(429)
    assert detect_block(resp) is BlockResult.HTTP_429

def test_detect_block_http_403():
    """ HTTP 403 também é tratado como bloqueio """
    resp = _fake_response(403)
    assert detect_block(resp) is BlockResult.HTTP_403
