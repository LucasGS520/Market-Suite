""" Renderização de templates de notificação usando Jinja2 """

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from market_alert.enums.enums_notifications import AlertType, NotificationChannel


TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates"

_environment = Environment(
    loader=FileSystemLoader(str(TEMPLATE_ROOT)),
    autoescape=False,
)

_SUBJECTS = {
    AlertType.price_change: "Mudança de preço detectada",
    AlertType.availability_change: "Mudança de disponibilidade detectada",
    AlertType.scraping_error: "Falha no scraping detectada",
    AlertType.custom: "Alerta personalizado",
}

_CHANNEL_EXTENSIONS = {
    NotificationChannel.webhook: "json",
}

def _template_name(channel: NotificationChannel, alert_type: AlertType) -> str:
    """ Resolve o caminho do template de acordo com o canal e tipo de alerta """
    extension = _CHANNEL_EXTENSIONS.get(channel, "txt")
    return f"{channel.value}/{alert_type.value}.{extension}"

def _fallback_template_name(channel: NotificationChannel) -> str:
    """ Retorna template genérico quando o específico não existir """
    extension = _CHANNEL_EXTENSIONS.get(channel, "txt")
    return f"{channel.value}/generic.{extension}"

def render_notification(
    *,
    channel: NotificationChannel,
    alert_type: AlertType,
    context: dict[str, Any],
) -> tuple[str | None, str | None]:
    """ Renderiza o conteúdo da notificação e o assunto quando aplicável """
    template_name = _template_name(channel, alert_type)
    try:
        template = _environment.get_template(template_name)
    except TemplateNotFound:
        #Fallback para manter entrega com template genérico quando não houver um específico
        template = _environment.get_template(_fallback_template_name(channel))

    message = template.render(**context)
    subject = _SUBJECTS.get(alert_type) if channel in {NotificationChannel.email, NotificationChannel.push} else None
    return subject, message
