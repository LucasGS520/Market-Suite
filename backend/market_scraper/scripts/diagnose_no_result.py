""" Ferramenta de diagnóstico para investigar respostas ``no_result`` do scraper.

O script reproduz a identidade HTTP do serviço oficial, baixa o HTML bruto
recebido para cada URL, executa os parsers principais e registra os motivos
pelos quais o ``DataQualityValidator`` aceitou ou rejeitou os payloads.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import shutil
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

import httpx

from market_scraper.core.config_scraper import settings
from market_scraper.utils.user_agents import compose_headers, get_user_agent
from market_scraper.utils.validator import DataQualityValidator, ValidationResult
from market_scraper.services.pipeline_factory import build_context, create_pipeline


ParserFn = Callable[[str, str], dict[str, Any] | None]

@dataclass(slots=True)
class ParserReport:
    """ Representa o estado final de um parser após validação de qualidade."""

    status: str
    raw_payload: dict[str, Any] | None
    validated_payload: dict[str, Any] | None
    validation_issue: dict[str, str] | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """ Converte o relatório para dicionário serializável em JSON."""

        payload: dict[str, Any] = {"status": self.status}
        if self.raw_payload is not None:
            payload["raw_payload"] = self.raw_payload
        if self.validated_payload is not None:
            payload["validated_payload"] = self.validated_payload
        if self.validation_issue is not None:
            payload["validation_issue"] = self.validation_issue
        if self.error is not None:
            payload["error"] = self.error
        return payload

class DiagnosticValidator(DataQualityValidator):
    """ Extensão do validador que registra o último motivo de rejeição."""

    def __init__(self) -> None:
        """ Inicializa estado interno para registrar rejeições detectadas."""

        super().__init__()
        self._last_issue: dict[str, str] | None = None

    def validate(
        self,
        *,
        step_name: str,
        payload: dict[str, Any] | None,
        url: str,
        source: str,
    ) -> dict[str, str] | None:
        """ Limpa o estado anterior e delega validação à implementação base."""

        #Zeramos o cache para garantir que o próximo relatório corresponda ao parser atual
        self._last_issue = None
        result: ValidationResult = super().validate(
            step_name=step_name,
            payload=payload,
            url=url,
            source=source,
        )
        if result.is_valid:
            return result.payload
        return None

    def _register_invalid(
        self, 
        step_name: str, 
        domain: str, 
        reason_code: str,
        reason_message: str,
        url: str,
        parser_name: str | None = None,
        dump_path: str | None = None,
        ) -> None:  # type: ignore[override]
        """ Salva o motivo de rejeição antes de propagar o registro padrão."""

        #Capturamos dados mínimos para explicar a decisão sem precisar inspecionar logs
        self._last_issue = {
            "reason": reason_code,
            "reason_message": reason_message,
            "domain": domain,
            "step": step_name,
            "parser_name": parser_name or "",
            "dump_path": dump_path or "",
        }
        super()._register_invalid(
            step_name,
            domain,
            reason_code,
            reason_message,
            url,
            parser_name,
            dump_path,
        )

    def consume_issue(self) -> dict[str, str] | None:
        """ Devolve o último motivo registrado e limpa o estado interno."""

        issue = self._last_issue
        self._last_issue = None
        return issue

def _build_timeout() -> httpx.Timeout:
    """ Replica timeouts configurados no serviço para aproximar o cenário real."""

    #Utilizamos a mesma granularidade de tempo para evitar falsos negativos em diagnósticos
    return httpx.Timeout(
        connect=settings.SCRAPER_HTTP_TIMEOUT_CONNECT,
        read=settings.SCRAPER_HTTP_TIMEOUT_READ,
        write=settings.SCRAPER_HTTP_TIMEOUT_WRITE,
        pool=settings.SCRAPER_HTTP_TIMEOUT_POOL,
    )

def _build_limits() -> httpx.Limits:
    """ Retorna limites de conexão equivalentes aos do scraper oficial."""

    #Limitamos conexões simultâneas para manter a carga próxima da produção
    return httpx.Limits(
        max_connections=settings.SCRAPER_HTTP_MAX_CONNECTIONS,
        max_keepalive_connections=settings.SCRAPER_HTTP_MAX_KEEPALIVE,
    )

def _build_referer(url: str) -> str | None:
    """ Monta o header Referer seguindo o template configurado via ambiente."""

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
        #Mantemos tolerância: templates inválidos não devem interromper o diagnóstico
        return None

def _compose_headers(url: str) -> dict[str, str]:
    """ Reproduz o conjunto de headers oficiais do serviço."""

    user_agent = get_user_agent(url)
    #Incluímos Referer apenas quando configurado, reproduzindo o comportamento do pipeline
    referer = _build_referer(url)
    return compose_headers(user_agent, referer=referer)

def _format_excerpt(html: str, length: int = 2048) -> str:
    """ Gera trecho compacto do HTML para inspeção manual em logs."""

    #Removemos quebras de linha para facilitar visualização em ferramentas de log
    excerpt = html[:length]
    return excerpt.replace("\n", " ").replace("\r", " ")

def _save_dump(content: bytes, output_dir: Path, url: str) -> Path:
    """ Persiste o HTML bruto em disco utilizando hash para rastreabilidade."""

    digest = hashlib.sha256(content).hexdigest()
    parsed = urlparse(url)
    domain = (parsed.hostname or "unknown").replace(".", "_")
    filename = f"{domain}_{digest[:12]}.html"

    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / filename
    #Gravamos bytes originais para possibilitar reprocessamento futuro
    target_path.write_bytes(content)
    return target_path

def _prepare_output_dir(output_dir: Path) -> None:
    """ Garante que o diretório de saída esteja limpo antes de um novo diagnóstico."""

    if output_dir.exists():
        for item in output_dir.iterdir():
            if item.is_dir():
                #Removemos pastas anteriores para evitar mistura de dumps entre execuções
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

def _run_parsers(
    html: str,
    url: str,
    validator: DiagnosticValidator,
    *,
    parsers: dict[str, ParserFn] | None = None,
) -> dict[str, Any]:
    """ Executa parsers configurados e aplica validação de qualidade."""

    if parsers is None:
        try:
            from market_scraper.parsers import parse_with_beautifulsoup, parse_with_extruct
        except ModuleNotFoundError as exc:  # pragma: no cover - dependência opcional ausente
            raise SystemExit(
                "Instale as dependências do market_scraper para executar os parsers reais"
            ) from exc

        parsers = {
            "parse_with_extruct": parse_with_extruct,
            "parse_with_beautifulsoup": parse_with_beautifulsoup,
        }

    results: dict[str, Any] = {}
    for name, parser in parsers.items():
        try:
            payload = parser(html, url)
        except Exception as exc:
            #Capturamos exceções para orientar investigações sem interromper o laço
            report = ParserReport(
                status="error",
                raw_payload=None,
                validated_payload=None,
                validation_issue=None,
                error=str(exc),
            )
            results[name] = report.to_dict()
            continue

        if not payload:
            report = ParserReport(
                status="empty",
                raw_payload=None,
                validated_payload=None,
                validation_issue=None,
                error=None,
            )
            results[name] = report.to_dict()
            continue

        validated = validator.validate(
            step_name=name,
            payload=payload,
            url=url,
            source=url,
        )
        if validated is not None:
            report = ParserReport(
                status="valid",
                raw_payload=payload,
                validated_payload=validated,
                validation_issue=None,
                error=None,
            )
            results[name] = report.to_dict()
            continue

        issue = validator.consume_issue()
        report = ParserReport(
            status="invalid",
            raw_payload=payload,
            validated_payload=None,
            validation_issue=issue,
            error=None,
        )
        results[name] = report.to_dict()

    return results

def _build_response_summary(
    url: str,
    response: httpx.Response,
    dump_path: Path,
    *,
    validator: DiagnosticValidator,
) -> dict[str, Any]:
    """ Cria dicionário consolidado com metadados e resultados de parsing."""

    html = response.text
    excerpt = _format_excerpt(html)
    parsers_summary = _run_parsers(html, url, validator)

    return {
        "url": url,
        "status_code": response.status_code,
        "content_type": response.headers.get("Content-Type"),
        "content_encoding": response.headers.get("Content-Encoding"),
        "dump_path": str(dump_path),
        "dump_hash": hashlib.sha256(response.content).hexdigest(),
        "html_excerpt": excerpt,
        "parsers": parsers_summary,
    }

def _load_urls(urls: Iterable[str], *, input_file: Path | None) -> list[str]:
    """ Combina URLs passadas por CLI com entradas lidas de arquivo."""

    collected = [item.strip() for item in urls if item.strip()]
    if input_file is not None and input_file.exists():
        file_urls = [line.strip() for line in input_file.read_text(encoding="utf-8").splitlines()]
        collected.extend(filter(None, file_urls))
    #Removemos duplicatas mantendo ordem para preservar contexto fornecido
    deduplicated: list[str] = []
    seen: set[str] = set()
    for item in collected:
        if item not in seen:
            deduplicated.append(item)
            seen.add(item)
    return deduplicated

def _parse_args() -> argparse.Namespace:
    """ Interpreta parâmetros CLI e prepara objetos auxiliares."""

    parser = argparse.ArgumentParser(
        description=(
            "Coleta HTML bruto, executa parsers locais e registra motivos de rejeição"
        )
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="Lista de URLs a diagnosticar (opcional quando --input-file é usado)",
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        help="Arquivo texto contendo uma URL por linha",
    )
    default_output = Path(__file__).parent / "diagnostics_output"
    parser.add_argument(
        "--output-dir",
        default=default_output,
        type=Path,
        help="Diretório onde os dumps de HTML serão armazenados (default: scripts/diagnostics_output)",
    )
    return parser.parse_args()

def _build_client() -> httpx.AsyncClient:
    """ Cria cliente HTTPx configurado com limites e timeouts oficiais."""

    #Ativamos follow_redirects para reproduzir o comportamento do pipeline de produção
    return httpx.AsyncClient(
        timeout=_build_timeout(),
        limits=_build_limits(),
        follow_redirects=True,
        max_redirects=settings.SCRAPER_HTTP_MAX_REDIRECTS,
    )

def _response_error_summary(url: str, error: Exception) -> dict[str, Any]:
    """ Gera resumo padronizado quando o download da página falha."""

    return {
        "url": url,
        "error": str(error),
    }

async def _run_pipeline_with_html(url: str, html: str) -> dict[str, Any]:
    """ Executa o pipeline oficial reutilizando um HTML já capturado."""

    pipeline = create_pipeline()
    context = build_context(url)
    #Atalhamos o download definindo o HTML manualmente, simulando o cache do pipeline
    context.set_html(html)
    outcome = await pipeline.run(context)
    steps = [
        {
            "name": step.name,
            "status": step.status,
            "duration_seconds": step.duration_seconds,
            "message": step.message,
        }
        for step in outcome.steps
    ]
    return {
        "status": outcome.status,
        "payload": outcome.payload,
        "steps": steps,
        "context": {
            "url": outcome.context.url,
            "source": outcome.context.source,
            "data": dict(outcome.context.data),
        },
    }

async def diagnose_url(
    client: httpx.AsyncClient,
    url: str,
    output_dir: Path,
    *,
    validator: DiagnosticValidator,
) -> dict[str, Any]:
    """ Executa diagnóstico completo para uma URL e retorna o relatório."""

    headers = _compose_headers(url)
    try:
        response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:  # pragma: no cover - guardamos contexto para análise manual
        #Quando falha o download, devolvemos erro explícito para guiar ajustes de rede
        return _response_error_summary(url, exc)

    dump_path = _save_dump(response.content, output_dir, url)
    return _build_response_summary(url, response, dump_path, validator=validator)

async def run_diagnostics(urls: list[str], output_dir: Path) -> list[dict[str, Any]]:
    """ Orquestra diagnósticos para todas as URLs informadas."""

    if not urls:
        return []

    validator = DiagnosticValidator()
    async with _build_client() as client:
        reports = []
        for url in urls:
            #Processamos sequencialmente para facilitar comparação manual de logs
            report = await diagnose_url(client, url, output_dir, validator=validator)
            reports.append(report)
    return reports

def main() -> None:
    """ Ponto de entrada CLI para geração dos relatórios de diagnóstico."""

    args = _parse_args()
    _prepare_output_dir(args.output_dir)
    urls = _load_urls(args.urls, input_file=args.input_file)
    reports = asyncio.run(run_diagnostics(urls, args.output_dir))

    for report in reports:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    # Assegura que o diretório de saída exista e grava um summary.json com todos os relatórios
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(reports, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":  # pragma: no cover - execução direta não é coberta em testes
    main()