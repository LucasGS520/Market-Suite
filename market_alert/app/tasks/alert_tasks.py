""" Tarefas Celery dedicadas ao envio de alertas

O ``rate_limit`` configurado no decorador das tasks limita a frequência com
que cada worker pode iniciar envios de alerta. Esse controle não altera o
agendamento de rechecagem de preços, apenas impede execuções excessivas do
mesmo worker.
"""

from uuid import UUID
from datetime import datetime, timezone
import time
import structlog

from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from infra.db import SessionLocal
from app.crud.crud_monitored import get_monitored_product_by_id
from app.crud.crud_user import get_user_by_id
from app.models.models_alerts import NotificationLog
from app.notifications.manager import NotificationManager, dispatch_price_alerts
from app.notifications.channels import EmailChannel, SMSChannel, PushChannel, WhatsAppChannel, SlackChannel
from app.enums.enums_alerts import ChannelType
from app.core.config import settings
from app import metrics


logger = structlog.get_logger("alert_tasks")

CHANNEL_MAP = {
    ChannelType.EMAIL: EmailChannel,
    ChannelType.SMS: SMSChannel,
    ChannelType.PUSH: PushChannel,
    ChannelType.WHATSAPP: WhatsAppChannel,
    ChannelType.SLACK: SlackChannel,
    ChannelType.WEBHOOK: SlackChannel
}

@celery_app.task(bind=True, max_retries=3, default_retry_delay=10, name="send_alert_task", rate_limit=settings.ALERT_RATE_LIMIT, queue="monitor")
def send_alert_task(self, notification_log_id: str) -> None:
    """ Dispara o envio de uma notificação já registrada """
    #Cria uma sessão de banco de dados
    db: Session = SessionLocal()
    try:
        #Recupera o registro de notificação e o usuário associado
        log = db.get(NotificationLog, UUID(notification_log_id))
        if not log:
            raise ValueError(f"NotificationLog {notification_log_id} not found")

        user = get_user_by_id(db, log.user_id)
        channel_cls = CHANNEL_MAP.get(log.channel)
        if not channel_cls:
            raise ValueError(f"Unsupported channel {log.channel}")

        #Instancia o canal de envio e o gerenciador de notificações
        channel = channel_cls()
        manager = NotificationManager([channel])

        #Tempo inicial para cálculo de métricas
        start = time.time()
        try:
            manager.send(
                db,
                user,
                log.subject,
                log.message,
                alert_rule_id=str(log.alert_rule_id) if log.alert_rule_id else None,
                alert_type=log.alert_type
            )
            success = True
            error = None
        except Exception as exc:
            success = False
            error = str(exc)
            log.success = success
            log.error = error
            log.sent_at = datetime.now(timezone.utc)
            metrics.NOTIFICATION_SEND_DURATION_SECONDS.labels(
                channel=log.channel.value
            ).observe(time.time() - start)
            db.commit()
            logger.error("alert_send_failed", channel=log.channel.value, error=error)
            raise self.retry(exc=exc)

        #Atualiza o log de envio com o resultado
        log.success = success
        log.error = error
        log.sent_at = datetime.now(timezone.utc)
        metrics.NOTIFICATION_SEND_DURATION_SECONDS.labels(channel=log.channel.value).observe(
            time.time() - start
        )
        db.commit()

    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc)
    finally:
        db.close()

@celery_app.task(bind=True, max_retries=3, default_retry_delay=10, name="send_notification_task", rate_limit=settings.ALERT_RATE_LIMIT, queue="monitor")
def send_notification_task(self, monitored_id: str, alerts: list) -> None:
    """ Envia notificações de preço para o produto monitorado informado """
    #Sessão para acesso ao banco de dados
    db: Session = SessionLocal()
    try:
        monitored = get_monitored_product_by_id(db, UUID(monitored_id))
        if not monitored:
            raise ValueError(f"Monitored product {monitored_id} not found")

        #Dispara as notificações para todos os canais configurados
        dispatch_price_alerts(db, monitored, alerts)

    except Exception as exc:
        raise self.retry(exc=exc)
    finally:
        db.close()

@celery_app.task(bind=True, max_retries=3, default_retry_delay=10, name="dispatch_price_alert_task", rate_limit=settings.ALERT_RATE_LIMIT, queue="monitor")
def dispatch_price_alert_task(self, monitored_id: str, alert: dict) -> None:
    """ Envia um unico alerta para um produto monitorado """
    #Sessão para acesso ao banco de dados
    db: Session = SessionLocal()
    try:
        monitored = get_monitored_product_by_id(db, UUID(monitored_id))
        if not monitored:
            raise ValueError(f"Monitored product {monitored_id} not found")

        #Envia apenas o alerta especificado
        dispatch_price_alerts(db, monitored, [alert])

    except Exception as exc:
        raise self.retry(exc=exc)
    finally:
        db.close()
