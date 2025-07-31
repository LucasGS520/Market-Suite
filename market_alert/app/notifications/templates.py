""" Modelos de mensagens para os alertas utilizando Jinja2 """

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

#Diretório de templates localizado em 'templates/notifications' na raiz do projeto
TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates" / "notifications"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"])
)

def _currency(value: Any) -> str:
    if value is None:
        return ""
    return f"R$ {Decimal(value):.2f}"

def _signed_decimal(value: Any) -> str:
    if value is None:
        return ""
    return f"{Decimal(value):+,.2f}".replace(",", ".")

#Registra filtros no ambiente Jinja
env.filters["currency"] = _currency
env.filters["signed_decimal"] = _signed_decimal

def _render(template_base: str, context: dict[str, Any], html: bool = False) -> str:
    suffix = "html" if html else "txt"
    template_name = f"{template_base}.{suffix}.j2"
    template = env.get_template(template_name)
    return template.render(**context)

def render_price_alert(monitored, alert: dict, html: bool = False) -> str:
    """ Renderiza alerta de preço """
    return _render("price_alert", {"monitored": monitored, "alert": alert}, html)

def render_price_change_alert(monitored, alert: dict, html: bool = False) -> str:
    """ Renderiza alerta de variação de preço """
    return _render("price_change_alert", {"monitored": monitored, "alert": alert}, html)

def render_listing_alert(monitored, alert: dict, html: bool = False) -> str:
    """ Renderiza alerta de listagem pausada ou removida """
    return _render("listing_alert", {"monitored": monitored, "alert": alert}, html)

def render_error_alert(monitored, alert: dict, html: bool = False) -> str:
    """ Renderiza alerta de erro de scraping ou interno """
    return _render("error_alert", {"monitored": monitored, "alert": alert}, html)
