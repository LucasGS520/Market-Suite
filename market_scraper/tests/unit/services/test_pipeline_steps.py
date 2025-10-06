from __future__ import annotations

import pytest

from market_scraper.services.pipeline_steps import (
    FetchHTMLStep,
    GenericFallbackParserStep,
    HtmlMetadataParserStep,
    JsonLdParserStep,
)
from market_scraper.services.synergic_pipeline import PipelineContext


@pytest.fixture
def context() -> PipelineContext:
    return PipelineContext(
        url="https://exemplo.com/produto",
        source="exemplo.com",
        default_step_timeout=0.5,
    )

@pytest.mark.asyncio
async def test_fetch_html_reuses_existing_content(context) -> None:
    """ Quando o HTML já está no contexto a etapa deve evitar download """
    context.set_html("<html></html>")
    step = FetchHTMLStep()
    result = await step.run(context)
    assert result.status == "success"
    assert "já presente" in (result.message or "")

@pytest.mark.asyncio
async def test_jsonld_parser_extracts_payload(context) -> None:
    """ Extrai dados a partir de JSON-LD disponível na página """
    context.set_html(
        """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Product", "name": "Produto", "offers": {"price": "50"}}
        </script>
        </head></html>
        """
    )
    step = JsonLdParserStep()
    result = await step.run(context)
    assert result.status == "success"
    assert result.payload["name"] == "Produto"
    assert result.payload["current_price"] == "50.00"
    assert context.data["name"] == "Produto"
 
@pytest.mark.asyncio
async def test_generic_fallback_handles_missing_data(context) -> None:
    """ Confirma que a heurística retorna status vazio quando nada é encontrado """
    context.set_html("<html><body><p>sem preço</p></body></html>")
    step = GenericFallbackParserStep()
    result = await step.run(context)
    assert result.status == "empty"

@pytest.mark.asyncio
async def test_html_metadata_parser_uses_meta_tags(context) -> None:
    """ Verifica extração simples com meta tags e elementos básicos """
    context.set_html(
        """
        <html>
            <head><meta property="og:title" content="Produto" /></head>
            <body><span class="price">R$ 99,90</span></body>
        </html>
        """
    )
    step = HtmlMetadataParserStep()
    result = await step.run(context)
    assert result.status == "success"
    assert result.message == "Metadados HTML extraídos com sucesso"
    assert result.payload["name"] == "Produto"
    assert result.payload["current_price"] == "99.90"
    assert context.data["name"] == "Produto"
    assert context.data["current_price"] == "99.90"
    