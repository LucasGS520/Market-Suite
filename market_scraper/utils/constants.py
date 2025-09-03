""" Centralizado constantes e utilidades utilizadas nas requisições HTTP do scraper

Reúne listas de User-Agent, cabeçalhos stealth, cookies genéricos e parâmetros de
throttle/jitter que controlam a taxa de acesso aos sites monitorados.
Também disponibiliza função auxiliar para converter URLs do Mercado Livre
para o domínio mobile.
"""

from typing import Tuple, Union, Dict
from urllib.parse import urlparse, urlunparse
import random
from market_scraper.core.config_scraper import settings
from shared.utils.ml_url import PRODUCT_HOSTS


# ---------- LISTA DE USER AGENTS (DESKTOP E MOBILE) ----------
USER_AGENTS = [
    #Desktop
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv: 97.0) Gecko/20100101 Firefox/97.0",

    #Mobile
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15A372 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 13_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.127 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 9; Pixel 3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",

    #Crawlers
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (compatible; Bingbot/2.0; +http://www.bing.com/bingbot.htm)",
]

# ---------- STEALTH HEADERS PADRÃO ----------
STEALTH_HEADERS: Dict[str, str] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "DNT": "1",
    "Sec-GPC": "1",
    "Referer": "https://www.mercadolivre.com.br/",
    "User-Agent": random.choice(USER_AGENTS),
}

# ---------- COOKIES GENÉRICOS ----------
GENERIC_COOKIES: Dict[str, str] = {
    "cookieConsent": "true",
    "geoCountry": "BR",
    "webp": "1",
}

# ---------- DOMÍNIO MOBILE DO MERCADO LIVRE ----------
MOBILE_DOMAIN = "m.mercadolivre.com.br"

# ---------- PARÂMETROS PADRÃO DE THROTTLE / JITTER PARA O THROTTLE MANAGER ----------
#Quantos tokens são recarregados por segundo
THROTTLE_RATE: float = settings.THROTTLE_RATE

#Capacidade máxima do bucket (tokens)
THROTTLE_CAPACITY: float = settings.THROTTLE_CAPACITY

#Intervalo de jitter (segundos) aplicado a cada requisição
JITTER_RANGE: Tuple[float, float] = (settings.JITTER_MIN, settings.JITTER_MAX)

# ---------- FUNÇÃO UTILITÁRIA PARA CONVERTER URL "DESKTOP" EM "MOBILE" ----------
def to_mobile_url(url: Union[str, object]) -> str:
    """ Converte URLs do Mercado Livre para o domínio mobile

    Caso a URL não pertença ao Mercado Livre, ela é retornada sem
    modificações. O caminho é preservado e o host é sempre
    substituído por ``m.mercadolivre.com.br``.
    """

    url_str = str(url) #Garante que é uma string para o urlparse
    parsed = urlparse(url_str)
    host_parts = parsed.netloc.split(".")

    #Se não achar 'mercadolivre' no host, retorna a URL inalterada
    if "mercadolivre" not in host_parts:
        #Se já for mobile ou domínio diferente, mantém a URL original
        return url_str

    #Sempre substitui o host pelo domínio mobile, independentemente da rota
    new_netloc = MOBILE_DOMAIN

    #Monta a nova URL com o host corrigido mantendo o caminho intacto
    return urlunparse(parsed._replace(netloc=new_netloc))
