""" Utilitários compartilhados entre os serviços """

from .logging_utils import mask_identifier
from .exception_sanitization import sanitize_exception_message
from .scraper_metadata import ScraperMetadata, extract_scraper_metadata
from .scraper_response_normalizer import normalize_scraper_response
from .text_sanitization import sanitize_media_url, sanitize_text
from . import url_validation
from .url_validation import UrlIssue, canonicalize_product_url, check_url_compatibility, normalize_product_url
from .user_agents import UserAgentProvider

__all__ = [
    "mask_identifier",
    "sanitize_exception_message",
    "ScraperMetadata",
    "extract_scraper_metadata",
    "normalize_scraper_response",
    "sanitize_media_url",
    "sanitize_text",
    "url_validation",
    "UrlIssue",
    "check_url_compatibility",
    "normalize_product_url",
    "canonicalize_product_url",
    "UserAgentProvider",
]
