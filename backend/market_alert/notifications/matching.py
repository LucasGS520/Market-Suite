""" Auxiliar para avaliar se um alerta satisfaz uma regra """

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from market_alert.enums.enums_alerts import AlertType
from market_alert.enums.enums_products import ProductStatus


def alert_matches_rule(alert: dict, rule) -> bool:
    """ Retorna ``True`` se o alerta satisfaz a regra fornecida """
    if getattr(rule, "product_status", None) is not None:
        status = alert.get("status")
        if status != rule.product_status.value:
            return False

    if rule.rule_type == AlertType.PRICE_TARGET:
        if alert.get("type") not in (None, "price_event", "price_below_monitored"):
            return False
        price = alert.get("price")
        if price is None:
            return False
        if rule.threshold_value is not None:
            target = Decimal(str(rule.threshold_value))
            current = Decimal(str(price))
            if current > target:
                return False
            alert.setdefault("threshold_value", rule.threshold_value)
            if target:
                diff = target - current
                alert["pct_below_threshold"] = (
                    diff / target * Decimal("100")
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if rule.threshold_percent is not None:
            pct = alert.get("pct_below_monitored")
            if pct is None:
                return False
            pct_decimal = Decimal(str(pct))
            if pct_decimal < Decimal(str(rule.threshold_percent)):
                return False
        return True

    if rule.rule_type == AlertType.PRICE_CHANGE:
        if alert.get("type") not in ("price_increase", "price_decrease"):
            return False
        change = abs(alert.get("change", 0))
        if rule.threshold_value is not None and change < rule.threshold_value:
            return False
        if rule.threshold_percent is not None:
            old = alert.get("old_price") or 0
            pct_change = abs(change / old * 100) if old else 0
            if pct_change < rule.threshold_percent:
                return False
        return True

    if rule.rule_type == AlertType.LISTING_PAUSED:
        return alert.get("status") == "unavailable"

    if rule.rule_type == AlertType.LISTING_REMOVED:
        return alert.get("status") == "removed"

    if rule.rule_type == AlertType.SCRAPING_ERROR:
        return bool(alert.get("error") or alert.get("detail"))

    return False
