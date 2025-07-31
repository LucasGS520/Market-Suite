""" Exporta registros de auditoria para o Prometheus """

from fastapi import FastAPI, Response
from prometheus_client import CollectorRegistry, Counter, generate_latest, CONTENT_TYPE_LATEST
import os
import json

#Diretório base onde os arquivos de auditoria são gravados
from app.utils.audit_logger import AUDIT_DIR


app = FastAPI(
    title="Audit Exporter",
    description="Exporta os registros de auditoria para um arquivo JSON",
    version="1.0"
)

@app.get("/metrica")
def metrics() -> Response:
    """ Varre todos os arquivos JSON de AUDIT_DIR/YYYY-MM-DD/*.json """
    registry = CollectorRegistry(auto_describe=True)

    #Contador de registros de auditoria por stage
    records_counter = Counter(
        "audit_records_total",
        "Total de registros de auditoria lidos",
        ["stage"],
        registry=registry
    )

    #Contador de erros de auditoria por stage
    errors_counter = Counter(
        "audit_errors_total",
        "Total de registros de auditoria com erro",
        ["stage"],
        registry=registry
    )

    #Percorre recursivamente as pastas de datas
    if not os.path.isdir(AUDIT_DIR):
        #Diretório de auditoria ainda não existente
        data = generate_latest(registry)
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    for date_dir in os.listdir(AUDIT_DIR):
        date_path = os.path.join(AUDIT_DIR, date_dir)
        if not os.path.isdir(date_path):
            continue
        for filename in os.listdir(date_path):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(date_path, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    record = json.load(f)
                stage = record.get("stage", "unknown")
                records_counter.labels(stage=stage).inc()
            except Exception:
                errors_counter.labels(stage="unknown").inc()
                continue

    data = generate_latest(registry)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
