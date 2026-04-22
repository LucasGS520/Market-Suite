# Contrato HTTP Scraper — Checklist de Compatibilidade

**Versão:** v1  
**Implementação:** `shared.schemas.shared_schemas_scraper`  
**Política:** Mudanças aditivas (campos opcionais) são permitidas dentro de v1. Mudanças breaking exigem nova versão major.  
**Estado (Fases 1–4 concluídas):** `response_helpers.py` removida; módulos canônicos são `error_mapper`, `response_mapper`, `response_builder`. `ParseProductUseCase` ativo sob flag `SCRAPER_NEW_ORCHESTRATOR_ENABLED`. `LateBrowserEscalationStep` marcada deprecated (remoção em fase futura).

---

## 1. Endpoint

| Item | Valor Congelado |
|---|---|
| Método | `POST` |
| Caminho | `/scraper/parse` |
| Content-Type aceito | `application/json` |
| Content-Type respondido | `application/json` |

---

## 2. Schema de Entrada — `ParserRequest`

| Campo | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `url` | `AnyHttpUrl` | ✅ | Normalizada antes do pipeline; `https://` aplicado se ausente |
| `product_type` | `string` | ❌ | Opcional, ignorado se desconhecido |
| `user_id` | `any` | ❌ | Opcional, correlação de auditoria |
| `metadata` | `dict` | ❌ | Campos livres: `trace_id`, `correlation_id`, `monitored_id`, `competitor_id`, `force_refresh` |

---

## 3. Schema de Saída de Sucesso — `ParserResponse`

| Campo | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `name` | `string` | ❌ | Nome do produto extraído |
| `current_price` | `Decimal` | ❌ | Preço normalizado; `null` se indisponível ou inválido |
| `currency` | `string` | ❌ | Código de moeda (ex.: `BRL`) |
| `availability` | `bool` | ❌ | `true`/`false`/`null` |
| `last_status` | `string` | ❌ | Ex.: `removed`, `temporarily_unavailable` |
| `etag` | `string` | ❌ | ETag do payload armazenado |
| `not_modified` | `bool` | ❌ | |
| `url` | `string` | ❌ | URL normalizada processada |
| `source` | `string` | ❌ | Domínio/marketplace de origem |
| `payload` | `dict` | ❌ | Metadados adicionais aditivos (ex.: `acquisition`) |
| `no_result` | `bool` | ❌ | |

---

## 4. Schema de Erro — `ErrorResponse`

| Campo | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `message` | `string` | ✅ | Mensagem legível |
| `error_code` | `ScraperErrorCode` | ✅ | Código canônico (ver seção 5) |
| `trace_id` | `string` | ❌ | Propagado do `metadata.trace_id` ou gerado internamente |

---

## 5. Códigos de Erro Canônicos — `ScraperErrorCode`

| Código | HTTP | Cenário |
|---|---|---|
| `invalid_url` | 400 / 422 | URL inválida ou protocolo não suportado |
| `blocked_host` | 400 | Host privado ou bloqueado (SSRF) |
| `unsupported_by_robots` | 403 | Bloqueado por robots.txt (modo `block`) |
| `too_many_redirects` | 422 | Loop de redirecionamento |
| `anti_bot_page` | 429 | Página de proteção anti-bot detectada |
| `no_result` | 422 | Pipeline concluiu sem dados extraíveis |
| `pipeline_timeout` | 504 | Pipeline excedeu tempo limite global |

**Observação:** `rate_limiter_cooldown`, `playwright_timeout`, `playwright_fetch_error` e `pipeline_degraded` são mapeados internamente para os códigos e status acima via `_map_http_download_issue`.

---

## 6. Códigos de Status HTTP

| Status | Cenário |
|---|---|
| `200 OK` | Parse concluído com payload normalizado (sucesso ou indisponível explícito) |
| `304 Not Modified` | ETag/Last-Modified corresponde; sem corpo |
| `400 Bad Request` | URL inválida ou host bloqueado antes do pipeline |
| `403 Forbidden` | Bloqueado por robots.txt |
| `422 Unprocessable Entity` | No-result, redirecionamento excessivo ou URL inválida pós-pipeline |
| `429 Too Many Requests` | Anti-bot detectado ou cooldown de domínio |
| `503 Service Unavailable` | Fallback browser indisponível ou falha de fetch no browser |
| `504 Gateway Timeout` | Pipeline ou Playwright excedeu timeout |

---

## 7. Headers Obrigatórios em Todas as Respostas

| Header | Valor | Presença |
|---|---|---|
| `X-MarketScraper-Contract-Version` | `v1` | **Obrigatório em todas as respostas** |
| `X-MarketScraper-Cache-Status` | `miss` / `hit` / `revalidated` / `bypass` | Obrigatório em respostas 200 |

---

## 8. Headers de Cache Condicional

| Header de Entrada | Semantica |
|---|---|
| `If-None-Match` | ETag da última resposta conhecida pelo cliente |
| `If-Modified-Since` | Data da última resposta conhecida pelo cliente |

| Header de Saída | Semantica |
|---|---|
| `ETag` | Hash do payload armazenado |
| `Last-Modified` | Timestamp da última atualização armazenada |

**Comportamento congelado:**
- Se `force_refresh=true` no metadata → cache ignorado (`cache_status=bypass`).
- Se ETag/Last-Modified corresponde → `304` sem corpo (cabeçalhos de cache mantidos).
- Cache invalidado em erros de download (robots, redirects, anti-bot).

---

## 9. Telemetria Obrigatória no Payload `acquisition`

Presente em `ParserResponse.payload.acquisition` quando pipeline executou coleta:

| Campo | Tipo | Notas |
|---|---|---|
| `layer_used` | `string\|null` | `curl_cffi`, `playwright` ou `null` |
| `fallback_taken` | `bool` | `true` se Playwright foi acionado |
| `classification_reason` | `string\|null` | Motivo da classificação do conteúdo |
| `http_status` | `int\|null` | Status HTTP da aquisição |
| `anti_bot_detected` | `bool` | Anti-bot detectado na resposta |
| `anti_bot_pattern` | `string\|null` | Padrão identificado (ex.: `cloudflare_challenge`) |
| `anti_bot_bypassed` | `bool` | Anti-bot superado via fallback |
| `data_quality` | `string` | `normal`, `degraded_anti_bot` ou `browser_fallback` |

---

## 10. Checklist de Compatibilidade (validar antes de cada fase de refatoração)

- [ ] `POST /scraper/parse` aceita `ParserRequest` e retorna `ParserResponse` ou `ErrorResponse`
- [ ] Todos os status HTTP listados na seção 6 permanecem mapeados aos mesmos cenários
- [ ] `X-MarketScraper-Contract-Version: v1` presente em **todas** as respostas
- [ ] `X-MarketScraper-Cache-Status` presente em respostas 200
- [ ] `ErrorResponse` sempre contém `message`, `error_code` e `trace_id`
- [ ] Cache condicional (`304`) funciona com `If-None-Match` e `If-Modified-Since`
- [ ] `force_refresh=true` bypassa cache HTTP e pipeline
- [ ] Telemetria `acquisition` presente em respostas 200 quando pipeline executou coleta
- [ ] `trace_id` propagado de `metadata.trace_id` para `ErrorResponse.trace_id`
- [ ] URL normalizada (scheme `https://` aplicado) antes do pipeline
