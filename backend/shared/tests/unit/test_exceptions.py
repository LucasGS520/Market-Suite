""" Testes das exceções compartilhadas """

from shared.exceptions import ScraperError

def test_scraper_error_pickable():
    """ Garante que ``ScraperError`` pode ser serializado """
    import pickle

    err = ScraperError(status_code=400, detail="bad")
    dump = pickle.dumps(err)
    loaded = pickle.loads(dump)
    assert isinstance(loaded, ScraperError)
    assert loaded.status_code == 400
    assert loaded.detail == "bad"
