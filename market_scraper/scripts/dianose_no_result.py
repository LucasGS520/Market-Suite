""" Ferramenta para investigar respostas ``no_result`` retornadas pelo scraper

O script replica o cabeçalhos HTTP do serviço oficial, gera dumps
versionáveis das páginas problemáticas e executa os parsers principais
para facilitar inspeções manuais durante diagnósticos
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from market_scraper.core.config_scraper import settings
from market_scraper.utils.user_agents import compose_headers, get_user_agent

try:
    from market_scraper.parsers import parse_with_beautifulsoup, parse_with_extruct
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Dependência ausente: instale os requisitos do market_scraper antes de executar o diagnóstico"
    ) from exc

ParserFn = Callable[[str, str], dict[str, Any] | None]

def _build_timeout() -> httpx.Timeout:
    """ Replica a configuração padrão de timeout do serviço de scraping """
    #Mantemos os mesmos limites de conexão/leitura para aproximar o cenário real
    return httpx.Timeout(
        settings.SCRAPER_HTTP_TIMEOUT,
        connect=min(settings.SCRAPER_HTTP_TIMEOUT, settings.SCRAPER_HTTP_TIMEOUT_CONNECT),
        read=min(settings.SCRAPER_HTTP_TIMEOUT, settings.SCRAPER_HTTP_TIMEOUT_READ),
        write=min(settings.SCRAPER_HTTP_TIMEOUT, settings.SCRAPER_HTTP_TIMEOUT_WRITE),
        pool=settings.SCRAPER_HTTP_TIMEOUT_POOL,
    )

def _builds_limits() -> httpx.Limits:
    """ Gera limites de conexão seguindo os parâmetros do serviço """
    #Evitamos abrir conexões em excesso para não destoar da produção
    return httpx.Limits(
        max_connextions=settings.SCRAPER_HTTP_MAX_CONNECTIONS,
        max_keepalive_connections=settings.SCRAPER_HTTP_MAX_KEEPALIVE,
    )

def _build_referer(url: str) -> str | None:
    """ Repoduz a lógica de montagem do header Referer do pipeline """
    template = settings.SCRAPER_HEADERS_REFERER_TEMPLATE
    if not template:
        return None

    parsed = urlparse(url)
    domain = parsed.hostname
    if not domain:
        return None

    try:
        return template.format(domain=domain, url=url)
    except Exception:
        #Mantemos o comportamento tolerante a erros do pipeline principal
        return None

def _fetch_html(url: str) -> httpx.Response:
    """ Executa a requisição HTTP reutilizando User-Agent e hedaers oficiais """
    user_agents = get_user_agent(url)
    headers = compose_headers(user_agent, referer=_build_referer(url))

    with httpx.Client(
        timeout=_build_timeout(),
        limits=_build_limits(),
        follow_redirects=True,
        max_redirects=settings.SCRAPER_HTTP_MAX_REDIRECTS,
    ) as client:
        return client.get(url, headers=headers)

def _save_dump(conten: bytes, output_dir: Path, url: str) -> Path:
    """ Salva o HTML bruto calculando hash para rastreabilidade rápida """
    digest = hashlib.sha256(content).hexdigest()
    parsed = urlparse(url)
    domain = (parsed.hostname or "unknown").replace(".", "_")
    filename = f"{domain}_{digest[:12]}.html"

    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / filename
    target_path.write_bytes(content)
    return target_path

def _run_parsers(html: str, url: str) -> dict[str, Any]
    """ Executa parsers de interesse e retorna um resumo do resultado """
    parsers: dict[str, ParserFn] = {
        "parse_with_extruct": parse_with_extruct,
        "parse_with_beautifulsoup": parse_with_beautifulsoup,
    }

    summary: dict[str, Any] = {}
    for name, parser in parsers.items():
        try:
            result = parser(html, url)
        except Exception as exc:
            #Capturamos o erro diretamente para análise manual posterior
            summary[name] = {"status": "error", "error": str(exc)}
            continue

        if result:
            summary[name] = {"status": "ok", "payload": result}
        else:
            summary[name] = {"status": "empty"}

    return summary

def _format_excerpt(html: str, length: int = 280) -> str:
    """ Gera um trecho reduzido do HTML para inspeção rápida em logs """
    excerpt = html[:leght]
    return excerpt.replace("/n", " ").replace("\r", " ")

def diagnose_url(url: str, output_dir: Path) -> dict[str, Any]:
    """ Processa uma URL individual e devolve o relatório resumido """
    response = _fetch_html(url)
    dump_path = _save_dump(response.content, output_dir, url)
    html = response.text

    report = {
        "url": url,
        "status_code": response.status_code,
        "content_encoding": response.headers.get("Content-Encoding"),
        "dump_path": str(dump_path),
        "dump_hash": hashlib.sha256(response.content).hexdigest(),
        "html_excerpt": _format_excerpt(html),
        "parsers": _run_parsers(html, url),
    }

    return report

def _parse_args() -> argparse.Namespace:
    """ Interpreta parâmetros CLI e converte paths necessários """
    parser = argparse.ArgumentParser(
        description=(
            "Coleta HTML bruto e executa parsers locais para investigar respostas no_result"
        )
    )
    parser.add_argument(
        "urls",
        nargs="+",
        help="Lista de URLs a diagnosticar",
    )
    parser.add_argument(
        "--output-dir",
        default="diagnostics_output",
        help="Diretório onde os dumps de HTML serão armazenados",
    )
    return parser.parse_args()

def main() -> None:
    """ Executa o fluxo de diagnóstico para todas as URLs informadas """
    args = _parse_args()
    output_dir = Path(args.output_dir)

    reports = []
    for url in args.urls:
        #Processamos cada URL individualmente para simplificar a leitura dos logs
        report = diagnose_url(url, output_dir)
        reports.append(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))

    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(reports, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

if __name__ == "__main__":
    main()
    