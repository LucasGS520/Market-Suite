""" Auxiliar para avaliar se um alerta satisfaz uma regra """

from __future__ import annotations

from market_alert.enums.enums_alerts import AlertType
from market_alert.enums.enums_products import ProductStatus


def alert_matches_rule(alert: dict, rule) -> bool:
    """ Retorna ``True`` se o alerta satisfaz a regra fornecida """
    if getattr(rule, "product_status", None) is not None:
        status = alert.get("status")
        if status != rule.product_status.value:
            return False

    if rule.rule_type == AlertType.PRICE_TARGET:
        return alert.get("type") in (
            None,
            "price_event",
            "price_below_monitored",
            "price_increase",
            "price_decrease",
        )

    if rule.rule_type == AlertType.PRICE_CHANGE:
        return alert.get("type") in (
            "price_increase",
            "price_decrease",
            "price_below_monitored",
            "price_event",
        )

    if rule.rule_type == AlertType.LISTING_PAUSED:
        return alert.get("status") == "unavailable"

    if rule.rule_type == AlertType.LISTING_REMOVED:
        return alert.get("status") == "removed"

    if rule.rule_type == AlertType.SCRAPING_ERROR:
        return bool(alert.get("error") or alert.get("detail"))

    return False
