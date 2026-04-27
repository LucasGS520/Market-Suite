from __future__ import annotations

from market_scraper.collection.policy import CollectionPolicyAction, ResponseClassifierPolicy


def test_collection_policy_stops_unavailable_without_browser():
    decision = ResponseClassifierPolicy().classify(
        http_status=404,
        html="<html>not found</html>",
        error=None,
    )

    assert decision.action == CollectionPolicyAction.STOP_UNAVAILABLE
    assert decision.reason == "http_404_unavailable"
    assert decision.telemetry["http_status"] == 404


def test_collection_policy_escalates_empty_html_to_browser():
    decision = ResponseClassifierPolicy().classify(
        http_status=200,
        html="<html></html>",
        error=None,
    )

    assert decision.action == CollectionPolicyAction.ESCALATE_TO_BROWSER
    assert decision.reason == "html_empty"


def test_collection_policy_accepts_degraded_html_with_product_signals():
    html = (
        "<html><head>"
        "<script>var challenge='__cf_chl';</script>"
        "<script type='application/ld+json'>{\"@type\":\"Product\",\"offers\":{\"price\":\"99.90\"}}</script>"
        "</head><body>"
        + ("x" * 2048)
        + "</body></html>"
    )

    decision = ResponseClassifierPolicy().classify(
        http_status=200,
        html=html,
        error=None,
    )

    assert decision.action == CollectionPolicyAction.ACCEPT
    assert decision.reason == "anti_bot_degraded"
    assert decision.telemetry["anti_bot_pattern"] == "cloudflare_challenge"
