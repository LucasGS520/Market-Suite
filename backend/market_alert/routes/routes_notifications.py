""" Rotas e WebSocket para consumo de notificações em tempo real. """

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Request, WebSocket
from fastapi.exceptions import HTTPException
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect, WebSocketState

from shared.infra.db import SessionLocal, get_db
from shared.infra.redis_pubsub import RedisChannelSubscriber
from shared.metrics.metrics_notifications import NOTIFICATIONS_WS_REJECTED_TOTAL

from market_alert.core.jwt import verify_access_token
from market_alert.core.security import get_current_user
from market_alert.crud.crud_notification_logs import get_notification_logs
from market_alert.enums.enums_alerts import ChannelType
from market_alert.models.models_users import User
from market_alert.schemas.schemas_alert_rules import NotificationLogResponse


router = APIRouter(prefix="/notifications", tags=["Notificações"])
logger = structlog.get_logger("http_route")

PUBSUB_CHANNEL = "notifications"
WEBSOCKET_CLOSE_UNAUTHORIZED = 4401
WEBSOCKET_CLOSE_FORBIDDEN = 4403


class NotificationWebSocketManager:
    """Coordena conexões WebSocket e associações a canais de interesse."""

    def __init__(self) -> None:
        self._channel_map: Dict[str, Set[WebSocket]] = {}
        self._connections: Dict[WebSocket, Set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: str) -> Set[str]:
        """Aceita a conexão e inscreve o cliente no canal pessoal."""

        await websocket.accept()
        default_channel = f"user:{user_id}"
        async with self._lock:
            bound = self._connections.setdefault(websocket, set())
            bound.add(default_channel)
            watchers = self._channel_map.setdefault(default_channel, set())
            watchers.add(websocket)
        return {default_channel}

    async def subscribe(self, websocket: WebSocket, channels: List[str]) -> Set[str]:
        """Adiciona o websocket aos canais informados retornando os aceitos."""

        normalized = {channel for channel in channels if isinstance(channel, str) and channel}
        if not normalized:
            return set()

        async with self._lock:
            current = self._connections.get(websocket)
            if current is None:
                return set()

            for channel in normalized:
                current.add(channel)
                watchers = self._channel_map.setdefault(channel, set())
                watchers.add(websocket)

        return normalized

    async def unsubscribe(self, websocket: WebSocket, channels: List[str]) -> Set[str]:
        """Remove o websocket dos canais informados retornando os removidos."""

        normalized = {channel for channel in channels if isinstance(channel, str) and channel}
        if not normalized:
            return set()

        removed: Set[str] = set()
        async with self._lock:
            current = self._connections.get(websocket)
            if current is None:
                return set()

            for channel in normalized:
                if channel in current:
                    current.remove(channel)
                    removed.add(channel)
                    watchers = self._channel_map.get(channel)
                    if watchers is not None:
                        watchers.discard(websocket)
                        if not watchers:
                            self._channel_map.pop(channel, None)

            if not current:
                self._connections.pop(websocket, None)

        return removed

    async def disconnect(self, websocket: WebSocket) -> None:
        """Fecha a conexão e remove o websocket de todos os canais."""

        async with self._lock:
            channels = self._connections.pop(websocket, set())
            for channel in channels:
                watchers = self._channel_map.get(channel)
                if watchers is not None:
                    watchers.discard(websocket)
                    if not watchers:
                        self._channel_map.pop(channel, None)

        try:
            if websocket.application_state != WebSocketState.DISCONNECTED:
                await websocket.close()
        except RuntimeError:
            pass

    async def close_all(self) -> None:
        """Finaliza todas as conexões ativas, utilizado no shutdown."""

        async with self._lock:
            sockets = list(self._connections.keys())
        for websocket in sockets:
            await self.disconnect(websocket)

    async def broadcast(self, channel: str, message: Dict[str, Any]) -> None:
        """Envia ``message`` para todos os websockets inscritos no canal."""

        async with self._lock:
            targets = list(self._channel_map.get(channel, set()))

        if not targets:
            return

        payload = dict(message)
        payload.setdefault("channel", channel)

        for websocket in targets:
            try:
                await websocket.send_json(payload)
            except Exception as exc:  # pragma: no cover - falhas específicas de rede
                logger.warning("notifications_ws_send_failed", channel=channel, error=str(exc))
                await self.disconnect(websocket)


manager = NotificationWebSocketManager()
subscriber = RedisChannelSubscriber(PUBSUB_CHANNEL)
_forward_task: asyncio.Task | None = None


@router.on_event("startup")
async def _start_notifications_listener() -> None:
    """Inicializa a thread assinante e o despachante de eventos Redis."""

    global _forward_task
    loop = asyncio.get_running_loop()
    subscriber.start(loop=loop)
    if _forward_task is None or _forward_task.done():
        _forward_task = loop.create_task(_forward_redis_events())


@router.on_event("shutdown")
async def _stop_notifications_listener() -> None:
    """Encerra o despachante de eventos e fecha conexões websockets."""

    global _forward_task
    if _forward_task is not None:
        _forward_task.cancel()
        try:
            await _forward_task
        except asyncio.CancelledError:
            pass
        _forward_task = None

    subscriber.stop()
    await manager.close_all()


async def _forward_redis_events() -> None:
    """Loop que escuta eventos Redis e repassa aos canais conectados."""

    while True:
        try:
            event = await subscriber.get()
            channels = event.get("channels")
            delivered = False
            if isinstance(channels, list):
                for channel in channels:
                    if isinstance(channel, str) and channel:
                        await manager.broadcast(channel, event)
                        delivered = True

            if delivered:
                continue

            fallback: List[str] = []
            user_id = event.get("user_id")
            monitored_id = event.get("monitored_id")
            if isinstance(user_id, str) and user_id:
                fallback.append(f"user:{user_id}")
            if isinstance(monitored_id, str) and monitored_id:
                fallback.append(f"monitored:{monitored_id}")

            for channel in fallback:
                await manager.broadcast(channel, event)
        except asyncio.CancelledError:  # pragma: no cover - cancelamento esperado no shutdown
            break
        except Exception as exc:  # pragma: no cover - erros não previstos
            logger.error("notifications_forwarder_failed", error=str(exc))


def _extract_token(websocket: WebSocket) -> Optional[str]:
    """Busca o token JWT no query string ou no cabeçalho Authorization."""

    token = websocket.query_params.get("token")
    if token:
        token = token.strip()
        if token.lower().startswith("bearer "):
            return token.split(" ", 1)[1]
        return token

    header = websocket.headers.get("Authorization")
    if header and header.lower().startswith("bearer "):
        return header.split(" ", 1)[1]

    return None


def _get_user_from_token(token: str) -> tuple[Optional[User], Optional[str]]:
    """Valida o JWT informado e retorna o usuário associado quando ativo."""

    try:
        payload = verify_access_token(token)
    except HTTPException as exc:
        logger.warning("notifications_ws_token_invalid", error=str(exc.detail))
        return None, "invalid_token"

    user_id = payload.get("sub")
    if not user_id:
        logger.warning("notifications_ws_token_missing_sub")
        return None, "missing_sub"

    try:
        user_uuid = UUID(str(user_id))
    except (ValueError, TypeError):
        logger.warning("notifications_ws_token_invalid_sub", sub=str(user_id))
        return None, "invalid_sub"

    with SessionLocal() as db:
        user = db.get(User, user_uuid)
        if not user or not user.is_active:
            logger.warning("notifications_ws_user_not_found", user_id=str(user_uuid))
            return None, "user_inactive_or_missing"
        return user, None


async def _handle_client_message(
    websocket: WebSocket,
    message: Dict[str, Any],
    *,
    user: User,
) -> Dict[str, Any]:
    """Processa mensagens recebidas do cliente WebSocket e retorna o ack."""

    action = message.get("action")
    if action == "subscribe":
        raw_channels = message.get("channels")
        if not isinstance(raw_channels, list):
            return {"type": "error", "message": "Formato de canais inválido."}

        allowed: List[str] = []
        user_channel = f"user:{user.id}"
        for channel in raw_channels:
            if not isinstance(channel, str):
                continue
            channel = channel.strip()
            if not channel:
                continue
            if channel.startswith("user:") and channel != user_channel:
                continue
            allowed.append(channel)

        added = await manager.subscribe(websocket, allowed)
        return {"type": "subscribed", "channels": sorted(added)}

    if action == "unsubscribe":
        raw_channels = message.get("channels")
        if not isinstance(raw_channels, list):
            return {"type": "error", "message": "Formato de canais inválido."}
        removed = await manager.unsubscribe(websocket, raw_channels)
        return {"type": "unsubscribed", "channels": sorted(removed)}

    msg_type = message.get("type")
    if msg_type == "ping":
        return {"type": "pong", "ts": datetime.now(timezone.utc).isoformat()}

    return {"type": "error", "message": "Mensagem não reconhecida."}


@router.websocket("/ws")
async def notifications_stream(websocket: WebSocket) -> None:
    """Canal WebSocket que envia eventos de comparação e alertas em tempo real."""

    token = _extract_token(websocket)
    if not token:
        logger.warning("notifications_ws_missing_token")
        NOTIFICATIONS_WS_REJECTED_TOTAL.labels(reason="missing_token").inc()
        await websocket.close(code=WEBSOCKET_CLOSE_UNAUTHORIZED)
        return

    user, rejection_reason = _get_user_from_token(token)
    if user is None:
        reason = rejection_reason or "invalid_token_or_user"
        logger.warning("notifications_ws_forbidden", reason=reason)
        NOTIFICATIONS_WS_REJECTED_TOTAL.labels(reason=reason).inc()
        await websocket.close(code=WEBSOCKET_CLOSE_FORBIDDEN)
        return

    initial_channels = await manager.connect(websocket, str(user.id))
    await websocket.send_json(
        {
            "type": "connected",
            "user_id": str(user.id),
            "channels": sorted(initial_channels),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Formato inválido de JSON."})
                continue

            response = await _handle_client_message(websocket, message, user=user)
            await websocket.send_json(response)
    except WebSocketDisconnect:
        logger.info("notifications_ws_disconnected", user_id=str(user.id))
    except Exception as exc:  # pragma: no cover - erros não previstos
        logger.error("notifications_ws_error", user_id=str(user.id), error=str(exc))
    finally:
        await manager.disconnect(websocket)

@router.get("/logs", response_model=List[NotificationLogResponse])
def list_notification_logs(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    channel: Optional[ChannelType] = Query(None),
    success: Optional[bool] = Query(None),
    alert_rule_id: Optional[UUID] = Query(None),
    cursor: Optional[datetime] = Query(None),
    user=Depends(get_current_user)
):
    """ Lista os "logs" de notificações do usuário autenticado. """
    logger.info(
        "route_called",
        path=request.url.path,
        method=request.method,
        user_id=str(user.id),
        limit=limit,
        offset=offset,
    )

    logs = get_notification_logs(
        db,
        user.id,
        limit=limit,
        offset=offset,
        start=start,
        end=end,
        channel=channel,
        success=success,
        alert_rule_id=alert_rule_id,
        cursor=cursor,
    )
    logger.info(
        "route_completed",
        path=request.url.path,
        method=request.method,
        status="success",
        count=len(logs),
    )
    return logs
