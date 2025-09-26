import pytest
from validators import domain

from market_scraper.utils.robots_txt import RobotsTxtParser

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
    monkeypatch.setattr("shared.utils.redis_client.get_redis_client", lambda: redis)
    return redis

@pytest.fixture()
def mock_http(monkeypatch):
    """ Mocka requests.get para simular robots.txt """
    response = {}

    def fake_get(url, *args, **kwargs):
        ua = kwargs.get("headers", {}).get("User-Agent")
        class FakeResponse:
            def __init__(self, text, status_code=200):
                self.text = text
                self.status_code = status_code

        return response[(url, ua)]

    monkeypatch.setattr("requests.get", fake_get)
    return response

@pytest.fixture()
def no_redis(monkeypatch):
    monkeypatch.setattr("market_scraper.utils.robots_txt.get_redis_client", lambda: None)

@pytest.mark.asyncio
async def test_crawl_delay_user_agent_exact_and_wildcard(fake_redis, mock_http):
    robots_url = "https://example.com/robots.txt"
    ua_google = "Googlebot"
    ua_custom = "MyCustomBot"
    resp = type("Resp", (), {
        "text": """
        User-agent: Googlebot
        Crawl-delay: 10
        
        User-agent: *
        Crawl-delay: 5
        """,
        "status_code": 200
    })()
    mock_http[(robots_url, ua_google)] = resp
    mock_http[(robots_url, ua_custom)] = resp

    parser = RobotsTxtParser(base_url="https://example.com")
    parser.redis = fake_redis

    #Caso exato -> deve retornar 10
    delay = await parser.get_crawl_delay(ua_google)
    assert delay == 10

    #Outro agente qualquer -> wildcard 5
    delay2 = await parser.get_crawl_delay(ua_custom)
    assert delay2 == 5

    #Cada user-agent possui sua própria chave em cache
    assert f"{parser.cache_key}:{ua_google}" in fake_redis.store
    assert f"{parser.cache_key}:{ua_custom}" in fake_redis.store

@pytest.mark.asyncio
async def test_robots_txt_parser_uses_redis_cache(fake_redis, mock_http):
    robots_url = "https://cached.com/robots.txt"
    parser = RobotsTxtParser(base_url="https://cached.com")
    parser.redis = fake_redis
    ua = "AnyBot"
    cache_key = f"{parser.cache_key}:{ua}"

    #Primeira resposta vem do HTTP e é cacheada
    mock_http[(robots_url, ua)] = type("Resp", (), {
        "text": """
        User-agent: *
        Crawl-delay: 8
        """,
        "status_code": 200
    })()

    delay = await parser.get_crawl_delay(ua)
    assert delay == 8
    assert fake_redis.store.get(cache_key)

    #Remove o mock HTTP para garantir que cache está sendo usado
    del mock_http[(robots_url, ua)]

    #Segunda chamada deve retornar valor armazenado, não lançar erro
    delay2 = await parser.get_crawl_delay(ua)
    assert delay2 == 8

@pytest.mark.asyncio
async def test_cache_isolated_per_domain(fake_redis, mock_http):
    robots_url1 = "https://site1.com/robots.txt"
    robots_url2 = "https://site2.com/robots.txt"

    ua = "*"
    mock_http[(robots_url1, ua)] = type("Resp", (), {
        "text": "User-agent: *\nCrawl-delay: 3",
        "status_code": 200
    })()
    mock_http[(robots_url2, ua)] = type("Resp", (), {
        "text": "User-agent: *\nCrawl-delay: 7",
        "status_code": 200,
    })()

    parser1 = RobotsTxtParser(base_url="https://site1.com")
    parser1.redis = fake_redis
    parser2 = RobotsTxtParser(base_url="https://site2.com")
    parser2.redis = fake_redis

    d1 = await parser1.get_crawl_delay(ua)
    d2 = await parser2.get_crawl_delay(ua)

    assert d1 == 3
    assert d2 == 7
    assert f"{parser1.cache_key}:{ua}" in fake_redis.store
    assert f"{parser2.cache_key}:{ua}" in fake_redis.store

@pytest.mark.asyncio
async def test_is_allowed_handless_allow_and_disallow(fake_redis, mock_http):
    robots_url = "https://example.com/robots.txt"
    ua = "*"
    mock_http[(robots_url, ua)] = type("Resp", (), {
        "text": """
        User-agent: *
        Disallow: /privado/
        Allow: /privado/faq
        Allow: /publico/
        """,
        "status_code": 200
    })()

    parser = RobotsTxtParser(base_url="https://example.com")
    parser.redis = fake_redis

    assert await parser.is_allowed("/publico/pagina", ua) is True
    assert await parser.is_allowed("/privado/segredo", ua) is False
    assert await parser.is_allowed("/privado/faq", ua) is True

@pytest.mark.asyncio
async def test_is_allowed_respeita_user_agent_especifico(fake_redis, mock_http):
    """ Verifica se regras específicas de ``User-Agent`` têm precedência sobre o wildcard """
    robots_url = "https://ua.com/robots.txt"
    resp = type("Resp", (), {
        "text": """
         User-agent: Googlebot
        Disallow: /privado

        User-agent: *
        Allow: /
        """,
        "status_code": 200,
    })()
    mock_http[(robots_url, "Googlebot")] = resp
    mock_http[(robots_url, "MeuBot")] = resp

    parser = RobotsTxtParser(base_url="https://ua.com")
    parser.redis = fake_redis

    #Goglebot é bloqeuado
    assert await parser.is_allowed("/privado", "Googlebot") is False
    #Outros agentes são liberados pelo Wildcard
    assert await parser.is_allowed("/privado", "MeuBot") is True

@pytest.mark.asyncio
async def test_crawl_delay_sem_redis(no_redis, mock_http):
    robots_url = "https://noredis.com/robots.txt"
    ua = "*"
    mock_http[(robots_url, ua)] = type("Resp", (), {
        "text": "User-agent: *\nCrawl-delay: 4",
        "status_code": 200,
    })()

    parser = RobotsTxtParser(base_url="https://noredis.com")
    assert parser.redis is None

    delay = await parser.get_crawl_delay(ua)
    assert delay == 4

@pytest.mark.asyncio
async def test_is_allowed_sem_redis(no_redis, mock_http):
    robots_url = "https://noredis.com/robots.txt"
    ua = "*"
    mock_http[(robots_url, ua)] = type("Resp", (), {
        "text": """
        User-agent: *
        Disallow: /privado
        Allow: /publico
        """,
        "status_code": 200,
    })

    parser = RobotsTxtParser(base_url="https://noredis.com")
    assert parser.redis is None

    assert await parser.is_allowed("/publico/pagina", ua) is True
    assert await parser.is_allowed("/privado/segredo", ua) is False

@pytest.mark.asyncio
async def test_disallow_rule_without_trailing_slash(fake_redis, mock_http):
    """ Garante que regras simples bloqueiam caminhos exatos sem afetar outros """
    robots_url = "https://example.com/robots.txt"
    ua = "*"
    mock_http[(robots_url, ua)] = type("Resp", (), {
        "text": """
        User-agent: *
        Disallow: /search
        """,
        "status_code": 200,
    })()

    parser = RobotsTxtParser(base_url="https://example.com")
    parser.redis = fake_redis

    assert await parser.is_allowed("/search", ua) is False
    assert await parser.is_allowed("/product", ua) is True
    