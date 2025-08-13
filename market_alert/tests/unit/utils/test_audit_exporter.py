from fastapi import FastAPI
from fastapi.testclient import TestClient

from market_alert.utils import audit_exporter


def test_app_instanciada():
    assert isinstance(audit_exporter.app, FastAPI)

    cliente = TestClient(audit_exporter.app)
    resposta = cliente.get("/")
    assert resposta.status_code == 404
