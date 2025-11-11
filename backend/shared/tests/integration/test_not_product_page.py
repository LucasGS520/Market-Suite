""" Testes de integração do scraper de concorrentes ao lidar com páginas sem produto válido """

from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.shared.schemas.shared_schemas_products import CompetitorProductCreateScraping
import pytest

try:
    from market_alert.services import services_scraper_competitor as mod
    scrape_competitor_product = mod.scrape_competitor_product
except Exception:
    pytestmark = pytest.mark.skip(reason="Dependências do market_alert indisponíveis")


def _payload() -> CompetitorProductCreateScraping:
    """ Monta payload padrão de produto concorrente """
    return CompetitorProductCreateScraping(
        #Campos obrigatórios definidos no esquema compartilhado
        monitored_product_id=str(uuid4()),
        product_url="https://example.com/item",
    )

def test_not_product_page_raises_bad_request():
    """ Garante que páginas sem produto retornam erro 400 """
    payload = _payload()

    with patch.object(
        mod.ScraperClient,
        "fetch",
        AsyncMock(side_effect=HTTPException(status_code=400)),
    ) as fetch_mock:
        with pytest.raises(HTTPException) as exc:
            scrape_competitor_product(
                db=Mock(spec=Session),
                url=payload.product_url,
                user_id=uuid4(),
                payload=payload,
            )

    assert exc.value.status_code == 400
    fetch_mock.assert_called_once()
