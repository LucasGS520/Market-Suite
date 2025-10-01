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
