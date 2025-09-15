""" Testes para seleção de etapas do pipeline por domínio """

from market_scraper.services.domain_policy import pipeline_steps_for
from market_scraper.services.pipeline_steps import (
    ExtructExtractionStep,
    ParselExtractionStep,
    BeautifulSoupExtractionStep,
    RequestsHTMLRenderStep,
    SelectorLibExtractionStep,
    MechanicalSoupLoginStep,
)


def test_pipeline_steps_ordem_por_dominio():
    """ Confere se a ordem de etapas para Mercado Livre está correta """
    url = "https://www.mercadolivre.com.br/produto"
    etapas = pipeline_steps_for(url)
    tipos = [type(e) for e in etapas]
    assert tipos == [
        ExtructExtractionStep,
        ParselExtractionStep,
        BeautifulSoupExtractionStep,
        RequestsHTMLRenderStep,
        SelectorLibExtractionStep,
        MechanicalSoupLoginStep,
    ]

def test_pipeline_steps_dominio_deconhecido():
    """ Domínios não configurados retornam lista vazia """
    etapas = pipeline_steps_for("https://dominio-inexistente.com/item")
    assert etapas == []
    