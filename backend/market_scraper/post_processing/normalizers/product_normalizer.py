""" Normalização de campos de produto: nome, source e URL. """

from __future__ import annotations

from typing import Any


class ProductNormalizer:
    """ Normaliza campos textuais do produto extraído."""

    def normalize_name(self, raw: Any) -> str | None:
        if not raw:
            return None
        stripped = str(raw).strip()
        return stripped or None

    def normalize_source(
        self,
        payload: dict[str, Any],
        fallback: str | None = None,
    ) -> str:
        return (
            payload.get("source")
            or payload.get("marketplace")
            or fallback
            or ""
        )

    def normalize_url(self, url: str) -> str:
        return url.strip() if url else ""


__all__ = ["ProductNormalizer"]
