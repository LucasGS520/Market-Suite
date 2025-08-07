from types import SimpleNamespace
from alert_app.notifications.templates import render_price_alert, render_price_change_alert, render_listing_alert, render_error_alert

def test_render_price_alert_includes_information():
    monitored = SimpleNamespace(name_identification="Produto X")
    alert = {"name": "Loja Y", "price": 10.0, "pct_below_target": 5}

    msg = render_price_alert(monitored, alert)

    assert "Produto X" in msg
    assert "Loja Y" in msg

    html = render_price_alert(monitored, alert, html=True)
    assert "<strong>" in html

def test_render_price_change_alert_has_old_and_new_prices():
    monitored = SimpleNamespace(name_identification="Prod")
    alert = {
        "name": "Shop",
        "price": 12.0,
        "old_price": 10.0,
        "change": 2.0,
        "type": "price_increase"
    }
    msg = render_price_change_alert(monitored, alert)
    assert "R$ 12.00" in msg
    assert "R$ 10.00" in msg

    html = render_price_change_alert(monitored, alert, html=True)
    assert "<p>" in html

def test_render_listing_alert_mentions_status():
    monitored = SimpleNamespace(name_identification="Prod")
    alert = {"name": "Shop", "status": "removed"}
    msg = render_listing_alert(monitored, alert)
    assert "removida" in msg

    html = render_listing_alert(monitored, alert, html=True)
    assert "<p>" in html

def test_render_error_alert_includes_error_message():
    monitored = SimpleNamespace(name_identification="Prod")
    alert = {"error": "timeout"}
    msg = render_error_alert(monitored, alert)
    assert "timeout" in msg

    html = render_error_alert(monitored, alert, html=True)
    assert "<p>" in html
