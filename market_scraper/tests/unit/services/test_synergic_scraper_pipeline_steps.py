""" Testes de pipeline sinérgico de scraping """

import pytest

from market_scraper.services import (
    SynergicPipeline,
    ExtructExtractionStep,
    ParselExtractionStep,
    BeautifulSoupExtractionStep,
)

HTML_JSON_LD = """
<html><head>
<script type="application/ld+json">{"@type":"Product","name":"Produto X","offers":{"price":"R$ 10"}}</script>
</head><body><span id="price">R$ 10</span></body></html>
"""

HTML_ONLY_META = """
<html><head>
<meta property="og:title" content="Produto Y" />
</head><body><span id="price">R$ 20</span></body></html>
"""

HTML_SIMPLE = """
<html><head><title>Produto Z</title></head>
<body><span class="price">R$ 30</span></body></html>
"""

@pytest.mark.asyncio
async def test_pipeline_prioriza_extruct():
    """ Quando JSON-LD está presente, Extruct deve ser usado """
    pipeline = SynergicPipeline(steps=[ExtructExtractionStep(), ParselExtractionStep(), BeautifulSoupExtractionStep()])
    result = await pipeline.run(shared_context={"url": "https://exemplo.com", "html": HTML_JSON_LD})
    assert result["details"]["name"] == "Produto X"
    assert result["extraction_method"] == "ExtructExtractionStep"

@pytest.mark.asyncio
async def test_pipeline_fallback_parsel():
    """ Deve usar Parsel quando Extruct não encontrar dados """
    pipeline = SynergicPipeline(steps=[ExtructExtractionStep(), ParselExtractionStep(), BeautifulSoupExtractionStep()])
    result = await pipeline.run(shared_context={"url": "https://exemplo.com", "html": HTML_ONLY_META})
    assert result["details"]["name"] == "Produto Y"
    assert result["extraction_method"] == "ParselExtractionStep"

@pytest.mark.asyncio
async def test_pipeline_fallback_beautifulsoup():
    """ Se Parsel falhar,  deve usar BeautifulSoup """
    pipeline = SynergicPipeline(steps=[ExtructExtractionStep(), ParselExtractionStep(), BeautifulSoupExtractionStep()])
    result = await pipeline.run(shared_context={"url": "https://exemplo.com", "html": HTML_SIMPLE})
    assert result["details"]["name"] == "Produto Z"
    assert result["extraction_method"] == "BeautifulSoupExtractionStep"

@pytest.mark.asyncio
async def test_pipeline_parallel_usa_primeiro_valido():
    """ Deve retornar o primeiro resultado válido no modo paralelo """
    pipeline = SynergicPipeline(steps=[ParselExtractionStep(), BeautifulSoupExtractionStep()])
    result = await pipeline.run(shared_context={"url": "https://exemplo.com", "html": HTML_SIMPLE}, execution_mode="parallel")
    assert result["details"]["name"] == "Produto Z"
    assert result["extraction_method"] == "BeautifulSoupExtractionStep"
