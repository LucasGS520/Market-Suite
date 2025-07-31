""" Registro detalhado das etapas de scraping para auditoria """

import os
import json
import time
import uuid
import structlog

from datetime import datetime, timezone
from fastapi.encoders import jsonable_encoder

from app.metrics import AUDIT_RECORDS_TOTAL, AUDIT_HTML_LENGTH_BYTES, AUDIT_RECORD_DURATION_SECONDS, AUDIT_ERRORS_TOTAL


logger = structlog.get_logger("audit_logger")

#Diretório base para os arquivos de auditoria
AUDIT_DIR = os.getenv("AUDIT_LOG_DIR", "logs/audit")

def _ensure_dir(path: str) -> None:
    """ Garante que o diretório exista """
    os.makedirs(path, exist_ok=True)

def audit_scrape( *, stage: str, url: str, payload: dict, html: str | None = None, details: dict | None = None, error: str | None = None) -> None:
    """ Grava um dump JSON de cada etapa do scraping para auditoria/debug """
    #Timestamp para organização
    start_time = time.time()
    now = datetime.now(timezone.utc)
    date_dir = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M-%S")

    #Monta o caminho final
    base_path = os.path.join(AUDIT_DIR, date_dir)
    _ensure_dir(base_path)

    filename = f"{time_str}_{uuid.uuid4().hex[:8]}_{stage}.json"
    filepath = os.path.join(base_path, filename)

    #Monta o objeto de auditoria
    record = {
        "timestamp": now.isoformat() + "z",
        "stage": stage,
        "url": url,
        "payload": payload,
        "html_length": len(html) if html is not None else None,
        "details": details,
        "error": error
    }

    #Emite métricas de contagem de registros
    AUDIT_RECORDS_TOTAL.labels(stage=stage).inc()

    #Emite métricas de tamanho de HTML
    if html is not None:
        AUDIT_HTML_LENGTH_BYTES.labels(stage=stage).observe(len(html))

    #Serializa e grava
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(jsonable_encoder(record), f, ensure_ascii=False, indent=2)
    except Exception as e:
        #Caso de erro de I/O, registra no logger para não interromper o fluxo
        AUDIT_ERRORS_TOTAL.labels(stage=stage).inc()
        logger.error("audit_write_failed", filepath=filepath, error=str(e))
        return

    #Emite métrica de latência de gravação
    duration = time.time() - start_time
    AUDIT_RECORD_DURATION_SECONDS.labels(stage=stage).observe(duration)
