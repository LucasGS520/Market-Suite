import pytest
from validators import domain

from app.utils.robots_txt import RobotsTxtParser

@pytest.fixture()
def fake_redis(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.store = {}

        def get(self, key):
            return self.store.get(key)

        def set(self, key, value, ex=None):
            self.store[key] = value

    redis = FakeRedis()
    monkeypatch.setattr("alert_app.utils.redis_client.get_redis_client", lambda: redis)
    return redis

@pytest.fixture()
def mock_http(monkeypatch):
    """ Mocka requests.get para simular robots.txt """
    response = {}

    def fake_get(url, *args, **kwargs):
        class FakeResponse:
            def __init__(self, text, status_code=200):
                self.text = text
                self.status_code = status_code

        return response[url]

    monkeypatch.setattr("requests.get", fake_get)
    return response

def test_crawl_delay_user_agent_exact_and_wildcard(fake_redis, mock_http):
    robots_url = "https://example.com/robots.txt"
    mock_http[robots_url] = type("Resp", (), {
        "text": """
        User-agent: Googlebot
        Crawl-delay: 10
        
        User-agent: *
        Crawl-delay: 5
        """,
        "status_code": 200
    })()

    parser = RobotsTxtParser(base_url="https://example.com")
    parser.redis = fake_redis

    #Chave de cache deve incluir o domínio
    expected_key = parser.cache_key

    #Caso exato -> deve retornar 10
    delay = parser.get_crawl_delay("Googlebot")
    assert delay == 10

    #Outro agente qualquer -> wildcard 5
    delay2 = parser.get_crawl_delay("MyCustomBot")
    assert delay2 == 5

    #Conteúdo foi salvo usando a chave de domínio
    assert expected_key in fake_redis.store

def test_robots_txt_parser_uses_redis_cache(fake_redis, mock_http):
    robots_url = "https://cached.com/robots.txt"
    parser = RobotsTxtParser(base_url="https://cached.com")
    parser.redis = fake_redis
    cache_key = parser.cache_key

    #Primeira resposta vem do HTTP é cacheada
    mock_http[robots_url] = type("Resp", (), {
        "text": """
        User-agent: *
        Crawl-delay: 8
        """,
        "status_code": 200
    })()

    delay = parser.get_crawl_delay("AnyBot")
    assert delay == 8
    assert fake_redis.store.get(cache_key)

    #Remove o mock HTTP para garantir que cache está sendo usado
    del mock_http[robots_url]

    #Segunda chamada deve retornar valor armazenado, não lançar erro
    delay2 = parser.get_crawl_delay("AnyBot")
    assert delay2 == 8

def test_cache_isolated_per_domain(fake_redis, mock_http):
    robots_url1 = "https://site1.com/robots.txt"
    robots_url2 = "https://site2.com/robots.txt"

    mock_http[robots_url1] = type("Resp", (), {
        "text": "User-agent: *\nCrawl-delay: 3",
        "status_code": 200
    })()
    mock_http[robots_url2] = type("Resp", (), {
        "text": "User-agent: *\nCrawl-delay: 7",
        "status_code": 200,
    })()

    parser1 = RobotsTxtParser(base_url="https://site1.com")
    parser1.redis = fake_redis
    parser2 = RobotsTxtParser(base_url="https://site2.com")
    parser2.redis = fake_redis

    d1 = parser1.get_crawl_delay("*")
    d2 = parser2.get_crawl_delay("*")

    assert d1 == 3
    assert d2 == 7
    assert parser1.cache_key in fake_redis.store
    assert parser2.cache_key in fake_redis.store
