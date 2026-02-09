""" Testes da renderização de templates de notificação """

from __future__ import annotations

from market_alert.enums.enums_notifications import AlertType, NotificationChannel
from market_alert.notifications.template_renderer import render_notification


def test_render_notification_retorna_assunto_e_mensagem() -> None:
    """ Valida renderização de template específico de email """
    subject, message = render_notification(
        channel=NotificationChannel.email,
        alert_type=AlertType.price_change,
        context={
            "user_name": "Maria",
            "monitored_name": "Produto X",
            "price_previous": "R$ 10,00",
            "price_current": "R$ 8,00",
            "price_delta_percent": 20,
            "trace_id": "trace-1",
            "event_id": "evt-1",
        },
    )

    assert subject == "Mudança de preço detectada"
    assert "Produto X" in message


def test_render_notification_fallback_generico_para_sms() -> None:
    """ Garante fallback para template genérico quando o específico não existe """
    subject, message = render_notification(
        channel=NotificationChannel.sms,
        alert_type=AlertType.custom,
        context={
            "user_name": "João",
            "monitored_name": "Produto Y",
            "event_id": "evt-2",
        },
    )

    assert subject is None
    assert message
    