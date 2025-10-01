# Cache Adapter Contract

Este documento descreve o contrato público do adaptador de cache/assinatura (CacheAdapter) que unifica as responsabilidades atuais de `IntelligentCacheManager` e `http_cache.ContentSignature`.

Decisão técnica
- API: async-first. Métodos async `async def ...`. Podemos expor wrappers síncronos apenas quando necessário.
- Prefixo de chaves: versionável (ex.: `scraper:product:v2:`).
- Serialização: JSON (consistentemente para Redis e local cache).
- Sentinel: usar `NOT_MODIFIED` (objeto único, compartilhado com o módulo `http_cache` enquanto migramos).

Métricas esperadas
- SCRAPER_CACHE_LOOKUPS_TOTAL{backend, outcome} (mantido)
- SCRAPER_CACHE_LATENCY_SECONDS{operation}
- SCRAPER_CACHE_LOCKS_ACQUIRED_total{operation}
- SCRAPER_CACHE_STAMPEDE_PREVENTED_total
- SCRAPER_CACHE_SIGNATURE_COMPARE_total{result}

API pública (métodos e assinaturas)

- class CacheAdapter (ou função factory retornando objeto)

  Métodos principais (async-first):

  - async def get(self, *, marketplace: str | None, url: str) -> Optional[dict[str, Any]]
    - Retorna o blob de cache previamente salvo ou None.
    - Formato esperado do valor retornado (compatível com implementação atual):
      {
        "data": {"name": str, "current_price": float, ...},
        "headers": {"etag": str | None, "last_modified": str | None}?,
        "metadata": {...}?
      }
    - Erros: não deve lançar em caso de Redis indisponível; retornar None e logar; métricas atualizadas.

  - async def set(self, *, marketplace: str | None, url: str, value: dict[str, Any], ttl: Optional[int] = None) -> None
    - Persiste o valor em Redis (setex) e atualiza fallback local.
    - Não deve lançar em caso de falha no Redis (logar e seguir), mas deve incrementar métricas de erro.

  - async def touch(self, *, marketplace: str | None, url: str, ttl: Optional[int] = None) -> None
    - Renova TTL no backend e no fallback local.

  - async def get_headers(self, url: str) -> dict[str, Optional[str]]
    - Retorna {"etag": str | None, "last_modified": str | None}

  - async def store_headers(self, url: str, *, etag: Optional[str] = None, last_modified: Optional[str] = None, ttl_seconds: Optional[int] = None) -> None
    - Persiste cabeçalhos relacionados ao recurso.

  - async def check_or_update_signature(self, url: str, html: str, *, domain: str | None = None) -> str | object
    - Calcula a assinatura (sha256) sobre o conteúdo normalizado por domínio.
    - Se o conteúdo não mudou, retorna o sentinel `NOT_MODIFIED`.
    - Caso contrário retorna a signature (str).

  - async def get_with_lock(self, key: str, compute_fn: Callable[..., Awaitable[dict]], lock_ttl: int = 30, wait_timeout: int = 10, early_recompute: bool = False) -> dict
    - Primitive para evitar cache stampede. Tenta ler o valor; em miss, adquire lock redis e executa `compute_fn` uma vez; outros aguardam até `wait_timeout` ou retornam valor stale.

Comportamentos e garantias
- Dual-read/versioning: o adaptador deve suportar leitura dual (v2 -> v1) para permitir migração sem perda de hits.
- Fallback local: quando Redis indisponível, usar `cachetools.TTLCache` para continuar operando.
- Locks: usar `redis.asyncio.Lock` (ou setnx+expire) com TTL seguro; sempre liberar lock em finally.
- Normalização: aplicar regras por domínio (configuráveis via `domain_policy.yaml`) antes de calcular assinatura.
- Segurança: não armazenar dados sensíveis em cache sem sanitização; logs devem ser sanitizados.

Erros e modos de falha
- Em caso de Redis indisponível: O adaptador deve logar o erro, incrementar métrica `outcome=error`, e usar fallback local; não propagar exceções ao caller.
- Em caso de falha ao calcular assinatura: retornar a assinatura recém calculada para evitar falsos NOT_MODIFIED; incrementar métrica `signature_compare=result=error`.

Notas de migração
- Primeiro lançar adaptador como facade (delegando para `IntelligentCacheManager` e `http_cache`) permitindo testes de integração.
- Ativar leitura via feature-flag e depois habilitar gravação.

Documentação adicional
- Incluir exemplos de uso no `market_scraper/README.md` e no `AGENTS.md`.
- Fornecer playbook de rollback (usar flag em `domain_policy.yaml` e prefix de chave para evitar colisões).

Call sites
---------

Lista (não exaustiva) de locais no código que atualmente dependem das funcionalidades do cache/assinatura e que devem ser atualizados para usar o `CacheAdapter`:

- `market_scraper/utils/intelligent_cache.py`
  - Define a classe `IntelligentCacheManager` com métodos `get`, `set`, `touch` e comportamento de fallback local. Métricas usadas: `SCRAPER_CACHE_LOOKUPS_TOTAL`, `SCRAPER_CACHE_LATENCY_SECONDS`, `SCRAPER_CACHE_LOCAL_SIZE`.
- `market_scraper/utils/http_cache.py`
  - Define `ContentSignature`, `get_cache_headers`, `store_cache_headers`, e sentinel `NOT_MODIFIED`. Usado para cálculo de assinatura, armazenamento de ETag/Last-Modified e comparação de conteúdo.
- `market_scraper/services/services_scraper_common.py`
  - Importa `IntelligentCacheManager` e `get_cache_headers`. Usa `cache_manager.set`, `cache_manager.get` e `cache_manager.touch` no fluxo de persistência e ao tratar `NOT_MODIFIED` retornado pelas etapas do pipeline.
- `market_scraper/services/pipeline_steps.py`
  - Exemplos de uso de `ContentSignature` via `ContentSignature(url).check_or_update(html)` e checagem explícita `is NOT_MODIFIED` para short-circuit do pipeline.
- `market_scraper/utils_controllers/pre_pipeline.py` e `market_scraper/utils_controllers/block_recovery.py`
  - Importam e recebem `IntelligentCacheManager` (injeção/uso dentro de orquestradores).
- `market_scraper/tests/unit/utils/test_intelligent_cache.py` e `market_scraper/tests/unit/utils/test_http_cache.py`
  - Testes unitários que exercitam o comportamento atual (mocks de `get_redis_client` e validações de decodificação/erros).
- `shared/utils/redis_client.py`
  - Implementa `get_redis_client()` usado por ambos `IntelligentCacheManager` e `http_cache`. Retorna cliente `redis.Redis` síncrono com `decode_responses=True`.

Observações sobre call sites
- A maioria dos usos atuais é síncrona (métodos `get/set/touch` em `IntelligentCacheManager` e funções em `http_cache`).
- Algumas integrações assumem bloqueio rápido (por exemplo, pipeline que chama `ContentSignature(...).check_or_update(html)` durante execução de etapa que já pode estar em contexto assíncrono). A migração para API async-first exigirá pequenos ajustes (usar `await` em pontos de I/O) ou wrappers síncronos que chamem o adaptador async via loop existente.

Decisão técnica final
--------------------

- Confirmamos a decisão inicial: o `CacheAdapter` será async-first (métodos `async def ...`) e implementará `redis.asyncio` internamente para operações I/O. Racional:
  - O restante do scraper já contém código assíncrono (ex.: `scrape_product_common_async`, `SynergicPipeline` steps com `async def run`). Um adaptador async evita bloqueios e facilita uso direto em etapas assíncronas.
- Para compatibilidade com call sites síncronos existentes, o adaptador proverá wrappers síncronos leves (funções que executam o loop async internamente ou utilizam `asyncio.run`/`asyncio.get_event_loop().run_until_complete` de forma segura quando apropriado). Recomenda-se:
  1. Preferir adaptar call sites para async quando possível (melhor performance, simplicidade). Testes e PRs pequenos para converter `services_scraper_common.scrape_product_common` e pontos que atualmente chamam `IntelligentCacheManager` síncrono.
  2. Implementar wrappers síncronos apenas para pontos que não possam ser convertidos rapidamente (scripts de inicialização, utilitários simples, testes legacy). Esses wrappers devem documentar expectativa de bloqueio e uso restrito.

- Implementação do `CacheAdapter`:
  - Usar `redis.asyncio` para cliente Redis principal.
  - Manter `cachetools.TTLCache` como fallback local (síncrono) protegido por locks de thread quando necessário.
  - Fornecer `get/set/touch/get_headers/store_headers/check_or_update_signature/get_with_lock` conforme especificado (todos `async def`).
  - Exportar versões síncronas com sufixo `_sync` ou uma camada `sync_adapter = SyncWrapper(async_adapter)` para consumo explícito.

Observabilidade e métricas (confirmação)
-------------------------------------

- Métricas a preservar/expôr pelo adaptador:
  - `SCRAPER_CACHE_LOOKUPS_TOTAL{backend, outcome}` — incrementadas em operações `get` por backend (redis/local) e resultado (hit/miss/error/expired/unavailable).
  - `SCRAPER_CACHE_LATENCY_SECONDS{operation}` — histogramas por operação (`get`, `set`, `touch`, `signature_check`, `lock_wait`).
  - `SCRAPER_CACHE_LOCAL_SIZE` — gauge para número de entradas no fallback local.
  - `SCRAPER_CACHE_LOCKS_ACQUIRED_total{operation}` — contador para locks adquiridos no `get_with_lock`.
  - `SCRAPER_CACHE_STAMPEDE_PREVENTED_total` — contador incrementado quando concorrentes são impedidos por lock e recebem valor stale/esperam.
  - `SCRAPER_CACHE_SIGNATURE_COMPARE_total{result}` — contador (changed/not_changed/error).

Próximos passos sugeridos
------------------------

1. Criar o esqueleto do `CacheAdapter` em `market_scraper/utils/cache_adapter.py` como facade delegando para `IntelligentCacheManager`/`http_cache` (modo de compatibilidade). Incluir testes unitários básicos que substituem `get_redis_client` para simular Redis ausente/presente.
2. Converter call sites críticos para usar API async do adaptador (ex.: `RequestsHTMLRenderStep`, `services_scraper_common` onde possível).
3. Gradualmente habilitar gravação no adaptador (feature-flag) e remover uso direto de `IntelligentCacheManager`/`ContentSignature` após cobertura de testes.

# end of insert
