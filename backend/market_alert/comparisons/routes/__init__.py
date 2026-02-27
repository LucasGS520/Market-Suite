"""Facade de roteadores HTTP da feature de comparações."""

from market_alert.comparisons.routes.routes_comparisons import router as comparisons_router

__all__ = ["comparisons_router"]
