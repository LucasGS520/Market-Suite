""" Utilidades de idempotência apoiadas em Redis

Este módulo centraliza o uso de chaves ``Idempotency-Key`` aceitas pela API
HTTP e por tasks Celery. O objetivo é garantir que replays recebam a mesma
resposta sem reprocessar a operação. O armazenamento utiliza o padrão
``idemp:{Idempotency-Key}``, conforme política estabelecida nas tarefas.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import structlog

from shared.utils.redis_client import get_redis_operational


logger = structlog.get_logger("redis_idempotency")

@dataclass(slots=True)
class IdempotencyRecord:
    """ Representa o estado de uma chave de idempotência """
    is_new: bool
    owner: str | None
    response: Any | None
    status_code: int | None

class IdempotencyOwnershipError(RuntimeError):
    """ Erro lançado quando uma chave pertence a outro usuário """

def _compose_redis_key(namespace: str, key: str) -> str:
    """ Monta a chave interna utilizada no Redis """
    safe_namespace = namespace.strip().replace(" ", "_")
    return f"idemp:{safe_namespace}:{key}"

def _serialize_record(owner: str | None, response: Any | None, status_code: int | None) -> str:
    """ Serializa a estrutura interna para JSON aceitando valores arbitrários """
    payload = {
        "owner": owner,
        "response": response,
        "status_code": status_code,
    }
    try:
        return json.dumps(payload, default=str)
    except Exception as exc:  # pragma: no cover - defesa contra serializações inesperadas
        logger.warning("idempotency_serialization_failed", error=str(exc))
        return json.dumps({"owner": owner, "response": None, "status_code": status_code})

def _deserialize_record(raw_value: str | None) -> tuple[str | None, Any | None, int | None]:
    """ Converte o JSON armazenado em atributos estruturados """
    if not raw_value:
        return None, None, None
    try:
        data = json.loads(raw_value)
    except json.JSONDecodeError as exc:  # pragma: no cover - ruido externo
        logger.warning("idempotency_decode_failed", error=str(exc))
        return None, None, None
    return data.get("owner"), data.get("response"), data.get("status_code")

def register_idempotency_key(
    *,
    namespace: str,
    key: str | None,
    owner: str | None,
    ttl_seconds: int,
) -> IdempotencyRecord | None:
    """ Registra a ``Idempotency-Key`` e retorna o estado correspondente

    Quando o Redis estiver indisponível ou a chave não for enviada, a função
    retorna ``None`` permitindo que a rota siga com o fluxo normal. Se a chave
    já existir e pertencer ao mesmo usuário, o resultado anterior é retornado.
    Caso pertença a outra pessoa usuária, uma exceção ``IdempotencyOwnershipError``
    é lançada para que o chamador responda com ``409``.
    """
    if not key:
        return None

    client = get_redis_operational()
    if client is None:
        logger.info("idempotency_disabled", namespace=namespace, reason="redis_unavailable")
        return None

    redis_key = _compose_redis_key(namespace, key)
    record_payload = _serialize_record(owner, None, None)

    try:
        was_set = client.set(redis_key, record_payload, nx=True, ex=ttl_seconds)
    except Exception as exc:  # pragma: no cover - falhas de rede
        logger.warning("idempotency_register_failed", error=str(exc), namespace=namespace)
        return None

    if was_set:
        logger.info("idempotency_registered", namespace=namespace, key=key, owner=owner)
        return IdempotencyRecord(is_new=True, owner=owner, response=None, status_code=None)

    stored_owner, stored_response, stored_status = _deserialize_record(client.get(redis_key))

    if stored_owner and owner and stored_owner != owner:
        logger.warning(
            "idempotency_conflict",
            namespace=namespace,
            key=key,
            owner=owner,
            stored_owner=stored_owner,
        )
        raise IdempotencyOwnershipError("Chave de idempotência pertence a outro usuário")

    return IdempotencyRecord(
        is_new=False,
        owner=stored_owner,
        response=stored_response,
        status_code=stored_status,
    )

def store_idempotency_response(
    *,
    namespace: str,
    key: str | None,
    owner: str | None,
    ttl_seconds: int,
    response: Any,
    status_code: int,
) -> None:
    """ Atualiza o registro de idempotência com a resposta calculada """
    if not key:
        return

    client = get_redis_operational()
    if client is None:
        return

    redis_key = _compose_redis_key(namespace, key)

    try:
        stored_owner, _, _ = _deserialize_record(client.get(redis_key))
        if stored_owner and owner and stored_owner != owner:
            logger.warning(
                "idempotency_store_conflict",
                namespace=namespace,
                key=key,
                owner=owner,
                stored_owner=stored_owner,
            )
            return

        client.set(
            redis_key,
            _serialize_record(owner, response, status_code),
            ex=ttl_seconds,
        )
    except Exception as exc:  # pragma: no cover - evita que falhas de cache quebrem a rota
        logger.warning("idempotency_store_failed", error=str(exc), namespace=namespace)
