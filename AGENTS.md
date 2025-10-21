# AGENTS.md — Guia para Agentes de IA (MarketSuite)

Este arquivo é um guia específico para agentes de IA que interagem com o código do projeto MarketSuite. Ele complementa o `README.md` voltado a pessoas desenvolvedoras, oferecendo contexto operacional do repositório, listagem de serviços e tarefas, utilidades internas e boas práticas para automação e manutenção.

> Nota: Sempre que novos módulos, tarefas ou serviços forem introduzidos, este arquivo deve ser atualizado. O AGENTS.md é um documento vivo e deve refletir a realidade do projeto.

## Objetivo
- Descrever como agentes de IA devem navegar no repositório e usar os serviços disponíveis.
- Fornecer um ponto de referência para tarefas automatizadas, integrações e rotinas internas.
- Consolidar boas práticas para manter consistência e qualidade das automações.
- Melhorar a eficiência ao indicar onde buscar contexto (no `README.md`) e onde encontrar instruções operacionais (aqui).

---

## Referências
- `README.md`: arquitetura, setup humano e visão geral do projeto.
- `market_scraper/README.md`: detalhes e estratégias do microserviço de scraping.

## Como Usar Este Documento
- Use este arquivo para instruções operacionais e automação (rotas, tasks, métricas, inicialização de serviços).
- Para setup local, visão conceitual e instruções humanas, consulte o `README.md`.
- Evite duplicar conteúdo extenso: referencie os arquivos acima quando necessário.

## Sumário Rápido
- Visão Geral da Arquitetura e Serviços: resumo de serviços e como iniciar.
- Infra e Observabilidade: portas, métricas, Prometheus/Grafana/Loki.
- Diretrizes de Desenvolvimento para Agentes: tipagem, docstrings, testes, métricas.
- Tarefas e Comandos de Execução: pré-requisitos, .env, Docker e execução manual.
- Tarefas Celery disponíveis: assinaturas e efeitos das tasks.
- Exemplos de chamadas de API: autenticação, scraping, comparação.
- Como Manter o AGENTS.md Atualizado: rotina de revisão do documento.
- Checklist de Cobertura Essencial: verificação rápida antes de releases.

## Atualização rápida — Market Scraper enxuto
- A rota ativa para scraping é `POST /scraper/parse` (alias `/scrape/parse`) utilizando `ParserResponse` como contrato.
- O pipeline mínimo executa `FetchHTML` → `JsonLd` → `HtmlMetadata` → `GenericFallback`; todas as etapas ficam em `market_scraper/services/pipeline_steps.py` e utilizam singleflight permanente com retries simples (tenacity respeitando `Retry-After`).
- `domain_policy.py` e `domain_policy.yaml` foram movidos para `market_scraper/archive/` e não são carregados automaticamente. Reative-os apenas se precisar de políticas dinâmicas.
- O cache padrão é em memória com LRU/TTL e métricas (`SCRAPER_CACHE_LOOKUPS_TOTAL`, `SCRAPER_CACHE_HIT_RATE`, `SCRAPER_CACHE_EVICTIONS_TOTAL`). Os limites são ajustados por `SCRAPER_CACHE_TTL_SECONDS` e `SCRAPER_CACHE_MAX_ENTRIES`.
- Parâmetros essenciais ficam explícitos no `.env.market_scraper`: TTL e tamanho do cache em memória, retries HTTP (`2`), política de fallback de robots (`allow`) e TTL dos locks de singleflight. Ajustes adicionais devem ser tratados como opt-in e documentados no rollout. Consulte `docs/runbook_scraper.md` para o passo a passo de deploy e rollback.
- A identidade HTTP (User-Agent e headers) é centralizada em `market_scraper/utils/user_agents.py`. Ajuste `SCRAPER_USER_AGENT_POOL`, `SCRAPER_DEFAULT_USER_AGENT` e `SCRAPER_HEADERS_*` pelo `.env.market_scraper` antes de executar rollouts.
- `robots.txt` é respeitado antes do download e utiliza retries controlados; a política de fallback é fixa e permissiva (allow) para manter disponibilidade. Métricas ficam em `SCRAPER_ROBOTS_CHECK_TOTAL`.

## Visão Geral da Arquitetura e Serviços
Para o diagrama e detalhes de arquitetura, consulte `README.md`. Abaixo, um resumo operacional para agentes.

### API Principal — `market_alert`
- Função: expõe endpoints REST (FastAPI) para cadastro/gestão de monitoramentos, dispara tarefas assíncronas (Celery) e integra com PostgreSQL/Redis/observabilidade.
- Comunicação: recebe requisições de usuários; agenda tarefas no Celery (broker Redis); consulta o `market_scraper` via HTTP (`SCRAPER_SERVICE_URL`). Exposição de métricas quando aplicável (ex.: `/metrics`).
- Para agentes: prefira interagir via API para agendar coletas, rechecks e consultar status, evitando acoplamento direto ao worker.

### Worker Celery — `market_alert.core.celery_app`
- Função: processa tarefas intensivas em background (scraping, comparação de preços, notificações, métricas, limpeza de cache).
- Tarefas comuns: `collect_product_task`, `collect_competitor_task`, `compare_prices_task`, `dispatch_price_alert_task`, `send_notification_task`, `send_alert_task`.
- Comunicação: consome filas no Redis; acessa banco/Redis; chama `market_scraper` quando necessário.
- Para agentes: agende via API; evite invocar diretamente funções internas do worker.

### Agendador — Celery Beat
- Função: agenda execuções periódicas (rechecagem de produtos, coleta/limpeza de métricas e caches).
- Tarefas agendadas comuns: `collect_celery_metrics`, `cleanup_cache`, `recheck_monitored_products`, `recheck_competitor_products`.
- Comunicação: publica jobs nas filas do Celery (broker Redis).
- O `SynergicPipeline` (`market_scraper/services/synergic_pipeline.py`) executa o pipeline sequencial padrão (definido em `services/pipeline_steps.py`). As políticas dinâmicas por domínio estão arquivadas junto ao antigo `domain_policy.yaml`.
-  Para agentes: ajuste cron/intervalos nas configurações do Celery; evite criar rotinas paralelas conflitantes.

### Serviço de Scraping — `market_scraper`
- **Função:** microserviço FastAPI que recebe uma URL e retorna JSON leve (`name`, `current_price`, `url`, `source`). Nenhum dado é persistido localmente.
- **Comunicação:** recebe HTTP da API/Worker, executa o `SynergicPipeline` com as etapas sequenciais padrão e responde seguindo o contrato `ParseResponse`.
- **Referências essenciais:** `market_scraper/services/pipeline_steps.py`, `market_scraper/services/services_scraper_common.py`, `market_scraper/utils/robots.py`, `market_scraper/utils/cache.py`, `shared/metrics/metrics_scraper.py` e `market_scraper/README.md`

#### Pipeline padrão e fallback
- Ordem fixa: `FetchHTMLStep` → `JsonLdParserStep` → `HtmlMetadataParserStep` → `GenericFallbackParserStep`, utilizando `price-parser` como primeira heurística textual.
- `FetchHTMLStep` normaliza URL, verifica `robots.txt`, consulta singleflight e o cache em memória antes de baixar o HTML com `httpx` usando retries simples (até duas tentativas extras respeitando `Retry-After`).
- Cada parser valida o payload com `DataQualityValidator`; quando nenhum retorna resultado válido o endpoint responde com `no_result`.
- Métricas principais: `SCRAPER_STEP_SUCCESS_TOTAL`, `SCRAPER_STEP_LATENCY_SECONDS`, `SCRAPER_STEP_FALLBACK_TOTAL`, `SCRAPER_HTTP_RETRIES_TOTAL`, `SCRAPER_HTTP_RETRY_BACKOFF_SECONDS` e `SCRAPER_ROBOTS_CHECK_TOTAL`.

#### Validação, cache e segurança
- `market_scraper/utils/url_validation.py` garante que a URL pertença aos marketplaces suportados e bloqueia hosts privados (SSRF).
- `market_scraper/utils/http_utils.py` resolve endereços públicos com cache/timeout configuráveis (`SCRAPER_DNS_CACHE_TTL`, `SCRAPER_DNS_TIMEOUT`) e bloqueia IPs privados antes do download.
- `market_scraper/utils/robots.py` reutiliza `robots.txt` em cache por host, aplica retries simples, devolve `unsupported_by_robots` quando o acesso é negado e assume fallback permissivo documentado em falhas de download/parse.
- Cache padrão em memória usa LRU/TTL com métricas (`SCRAPER_CACHE_LOOKUPS_TOTAL`, `SCRAPER_CACHE_HIT_RATE`, `SCRAPER_CACHE_EVICTIONS_TOTAL`). Não há backend alternativo carregado por padrão.
- O arquivo `.env.market_scraper` lista apenas parâmetros de tuning (TTL, limites de cache e timeouts); mantenha os comentários desligados até ajustar limites HTTP específicos.

#### Contexto compartilhado e métricas
- O `PipelineContext` expõe `url`, `source`, `html` e `data` (payload final). Atualize apenas chaves documentadas (`name`, `current_price`, `url`, `source`, `payload`).
- Métricas ficam em `shared/metrics/metrics_scraper.py`. Sempre reutilize contadores existentes antes de criar novos.

#### Consolidação dos utilitários do `market_scraper`
- `market_scraper/utils/` mantém helpers puros (sem estado compartilhado). Esses módulos podem ser importados diretamente pelas etapas do pipeline sem depender de configuração global.
- Módulos de rede (`http_retry.py`, `singleflight.py`, `http_utils.py`) expõem funções reutilizáveis com métricas; preserve a API pública e parâmetros numéricos (`SCRAPER_HTTP_RETRIES`, `SCRAPER_DNS_TIMEOUT`) ao criar novos usos.
- `market_scraper/utils_controllers` concentra orquestradores com estado, evitando que cada etapa manipule diretamente recursos externos.
- `shared/utils` continua sendo a fonte para rotinas verdadeiramente compartilhadas. Sempre avalie se o helper pertence á camada comum antes de criar novos módulos no scraper.

**Boas práticas ao criar/editar utilitários:**
- `market_scraper/utils/` armazena helpers puros (cache, robots, validação de URL, parsing de preço).
- `market_scraper/utils/price.py` utiliza o `price-parser` como primeira estratégia antes do fallback manual.
- `market_scraper/utils_controllers/` concentra componentes com estado (loaders/config). Avalie se o utilitário realmente precisa de estado antes de adicioná-lo aqui.
- `shared/utils` continua a fonte para funcionalidades cross-service (Redis, logging, normalização de URL). Prefira mover lógicas genéricas para lá.

**Testes de regressão dos utilitários:**
- `pytest market_scraper/tests/unit/utils -q`
- `pytest market_scraper/tests/unit/services -q`
- `pytest market_scraper/tests/integration/routes/test_parse.py -q`
- Utilize fixtures em `market_scraper/tests/fixtures/` para simular respostas de marketplaces quando necessário.

#### Checklist para novas etapas do pipeline
1. Criar a classe herdando de `PipelineStep` em `market_scraper/services/pipeline_steps.py` (ou módulo dedicado).
2. Registrar a etapa na função `default_pipeline_steps()` na posição desejada.
3. Adicionar testes unitários cobrindo a etapa isolada e integração via `test_parse.py` quando afetar o fluxo final.
4. Atualizar documentação (`market_scraper/README.md`, `README.md` e esta seção) descrevendo a nova etapa e métricas.
5. Revisar variáveis de ambiente/timeouts necessários e adicionar às instruções de configuração.

#### Segurança, compliance e limites
- Respeitar `robots.txt` antes de ativar novas políticas.
- Preservar a minimização de dados (LGPD/GDPR): coletar somente campos necessários ao alerta e mascarar quaisquer dados sensíveis nos logs (`shared/utils/logging.py`).
- Revisar limites externos (headers `Retry-After`, quotas por API pública) antes de aumentar o paralelismo.
- Evitar armazenar tokens/sessões em arquivos temporários; usar apenas o cache in-memory controlado.

#### Observabilidade de regressões
- Ativar dashboards específicos no Grafana acompanhando `SCRAPER_STEP_FALLBACK_TOTAL` vs. taxa de sucesso.
- Criar alertas no Prometheus quando `SCRAPING_LATENCY_SECONDS{le="5"}` sair da meta definida no README.
- Para diagnósticos rápidos, habilitar logs nível `debug` apenas em ambientes controlados {`structlog` com `contextvars`}.
- Sempre registrar no PR alterações no pipeline (`pipeline_steps.py`), configurações e métricas acompanhadas.

### Utilitários Compartilhados — `shared`
- Para agentes: reutilizar utilitários em novas tarefas/estratégias; evitar duplicar lógica existente.

### Infra e Observabilidade
- Componentes: PostgreSQL, Redis, Prometheus, Grafana, Loki/Promtail; orquestrados por `docker-compose.yml`.
- Métricas/logs: expostas quando aplicável (ex.: `/metrics`), coletadas centralmente e visualizadas no Grafana.
- Para agentes: monitorar filas Celery, tempos de execução e erros; usar métricas para decisões adaptativas (ex.: backoff, recheck).

#### Observabilidade e Métricas — Guia Operacional

- Serviços e portas (Docker Compose):
  - API (`market_alert`): `http://localhost:8000/metrics` → Prometheus scrape.
  - Celery Beat: `http://localhost:8001/metrics` → Prometheus scrape.
  - Celery Worker: `http://localhost:8002/metrics` → Prometheus scrape.
  - Prometheus: `http://localhost:9090` | Alertmanager: `http://localhost:9093` | Loki: `http://localhost:3100` | Grafana: `http://localhost:3000`.
  - Configurações: `shared/infra/prometheus/prometheus.yml:1`, `shared/infra/prometheus/alert_rules.yml:1`, `shared/infra/promtail/promtail-config.yml:1`, `shared/infra/loki/loki-config.yml:1`.

- Exposição de métricas por serviço:
  - API FastAPI: endpoint `GET /metrics` já implementado em `market_alert/main.py:162`. Coleta:
    - HTTP: `HTTP_REQUESTS_TOTAL`, `HTTP_REQUESTS_LATENCY_SECONDS`.
    - API: `API_ERRORS_TOTAL` (por endpoint/status).
    - DB pool: `DB_POOL_SIZE`, `DB_POOL_CHECKOUTS` (atualizados ao acessar `/metrics`).
    - Logs: `LOG_ENTRIES_TOTAL` via `structlog` em `market_alert/main.py:57`.
  - Celery Worker: servidor embutido Prometheus em `market_alert/core/celery_app.py:40` (`start_http_server` porta 8002). Coleta:
    - Tarefas: `CELERY_TASKS_TOTAL` (com status), `CELERY_TASK_DURATION_SECONDS`.
  - Celery Beat: servidor embutido Prometheus em `market_alert/beat_with_metrics.py:8` (porta 8001). Coleta periódica:
    - Filas/Workers/Redis: `CELERY_QUEUE_LENGTH`, `CELERY_WORKERS_TOTAL`, `CELERY_WORKER_CONCURRENCY`, `REDIS_MEMORY_USAGE_BYTES`, `REDIS_QUEUE_MESSAGES` em `market_alert/tasks/metrics_tasks.py:1`.
    - Scraper: utiliza contadores/histogramas em `shared/metrics/metrics_scraper.py:1` (ex.: `SCRAPING_LATENCY_SECONDS`, `SCRAPER_STEP_LATENCY_SECONDS`, `SCRAPER_CACHE_LOOKUPS_TOTAL`). Exposição HTTP dedicada não está ativa por padrão; as métricas aparecem quando importadas por serviços com endpoint `/metrics`.

- Coleta de logs estruturados:
  - API e Worker logam em JSON via `structlog` (incrementa `LOG_ENTRIES_TOTAL`).
  - Promtail envia logs ao Loki conforme `shared/infra/promtail/promtail-config.yml:1`. Visualização no Grafana (Data Source Loki) e correlação com métricas.

- Scrape configs prontas (Prometheus):
  - Jobs configurados em `shared/infra/prometheus/prometheus.yml:12` (`marketalert_app`, `marketalert_audit`, `marketalert_celery`, `marketalert_worker`).
  - Audit Exporter: rota `/audit/metrica` montada em `market_alert/main.py:174` (se habilitada) e referenciada no Prometheus.

- Consultas PromQL úteis:
  - Latência P95 API: `histogram_quantile(0.95, sum(rate(http_request_latency_seconds_bucket[5m])) by (le, endpoint))`
  - Erro por endpoint: `sum(rate(api_errors_total[5m])) by (endpoint, status_code)`
  - Backlog por fila: `celery_queue_length` e `redis_queue_messages`
  - Duração média de tasks: `sum(rate(celery_task_duration_seconds_sum[5m])) / sum(rate(celery_task_duration_seconds_count[5m]))`
  - Bloqueios scraper: `increase(scraper_http_blocked_total[15m])`

- Metas de desempenho (SLOs sugeridos):
  - API: P95 de `http_request_latency_seconds` < 300 ms; taxa de erro < 1% por endpoint.
  - Scraping: P95 de `scraping_latency_seconds` < 2.5 s; `scraper_http_blocked_total` ~0 com `block_recovery` efetivo.
  - Celery: P95 de `celery_task_duration_seconds` < 5 s; `celery_queue_length` estável sem crescimento sustentado por >10 min.
  - Redis: `redis_memory_usage_bytes` com headroom > 20%; filas sem picos contínuos.

- Boas práticas para agentes (autoajuste):
 - Use `SCRAPER_CACHE_LOOKUPS_TOTAL` e `SCRAPER_ROBOTS_CHECK_TOTAL` para correlacionar quedas de desempenho com bloqueios do site.
 - Ajuste cadência revisando `SCRAPER_STEP_TIMEOUT_SECONDS`, `SCRAPER_PIPELINE_TIMEOUT_SECONDS` e parâmetros de cache quando `SCRAPING_LATENCY_SECONDS` ou `SCRAPER_STEP_FALLBACK_TOTAL` indicarem degradação.
  - Condicione rechecagens com `AdaptiveRecheckManager` considerando `SCRAPER_RETRY_TOTAL` e variação recente de preço.

- Referências rápidas (FastAPI + Prometheus):
  - Prometheus Python client (exposição `/metrics`): https://github.com/prometheus/client_python
  - Instrumentação FastAPI pronta: https://github.com/trallard/prometheus-fastapi-instrumentator
  - OpenTelemetry para FastAPI/Celery: https://opentelemetry.io/docs/instrumentation/python/

## Diretrizes de Desenvolvimento para Agentes

- Linguagem e comentários: mantenha docstrings e comentários em português, descrevendo propósito, parâmetros, retornos e exceções. Evite comentários redundantes; foque em contexto e decisões. Siga esse padrão para comentários e Docstrings: (Ex: #Comentário Padrão vem seguido da Hastag, """ Docstrings possui espaço após incio e fim ").
- Tipagem: use type hints em todas as funções públicas; mantenha assinaturas estáveis ou com parâmetros opcionais para compatibilidade.
- Estrutura e estilo: siga o padrão existente do repositório; não introduza linters/formatadores novos sem alinhamento. Não use `print`; logue com `structlog` e incremente métricas quando aplicável.
- Testes: escreva/ajuste testes com `pytest`; prefira casos pequenos e parametrizados próximos do código alterado. Execute `pytest -q` antes de propor mudanças.
- Métricas: ao criar fluxos relevantes, exponha contadores/histogramas no pacote `shared/metrics/*` e reutilize nomes/padrões já existentes. Atualize `/metrics` quando necessário.
- Pesquisa no código: prefira `rg` (ripgrep) para buscas rápidas; se indisponível, use `grep -Rni` com exclusões de diretórios (`.venv`, `.git`, caches). Exemplos: `rg -n "metrics|/metrics"`, `rg -n "collect_.*_task" market_alert`.
- Commits: mantenha mensagens claras no formato do tipo de mudança (ex.: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`), sempre traga a frase utilizada para o commit ao final da resposta (Ex: feat: Add nova instrução ao AGENTS.md). Faça mudanças pequenas e coesas; referência arquivos/rotas afetadas. Evite criar branches sem necessidade ou renomear arquivos amplamente.
- Pull requests: prefira PRs curtos e focados com descrição objetiva do impacto (API, tasks, métricas, migrações). Inclua checklist de testes e validações manuais quando aplicável.
- Alteração de interfaces: tenha extrema cautela ao mudar contratos de API, esquemas Pydantic, assinaturas de tasks Celery e estruturas de resposta do scraper. Preserve retrocompatibilidade (parâmetros opcionais com default), documente deprecações e atualize `AGENTS.md`, `README.md` e testes.
- Banco e migrações: não modifique esquemas sem migrar via Alembic; descreva riscos e plano de rollback. Nunca apague dados em massa em rotinas automatizadas.
- Observabilidade: ao introduzir funcionalidades, inclua métricas relevantes (latência, contadores de erro, tamanhos de fila) e logs estruturados. Atualize `shared/infra/prometheus/alert_rules.yml` se o SLO for afetado.
- Segurança e segredos: nunca logue tokens/senhas; use `.env` e utilidades em `shared/infra` para acessar segredos. Evite hardcode de URLs/credenciais.
- Compatibilidade local/Docker: mantenha portas alinhadas ao `docker-compose.yml`; evite conflitos (ex.: métricas Beat 8001, Worker 8002, API 8000, Scraper 8010 em dev).
- Ao final de cada Sprint, Etapas ou Fases, trazer alertas para que haja atualização nos arquivos `README.md` e `AGENTS.md`.

### Fluxo Alto Nível
1) Usuário → `market_alert` (API) para criar monitoramentos/solicitar coletas.
2) `market_alert` agenda tarefas → Celery Worker (Redis como broker).
3) Worker consulta `market_scraper` quando necessário e persiste/atualiza dados.
4) Regras disparam notificações; observabilidade registra métricas/logs.
5) Celery Beat agenda rechecagens e rotinas de manutenção.

## Tarefas e Comandos de Execução

### Pré-requisitos
- Python 3.10 ou superior
- Docker e Docker Compose (para ambiente completo)
- Redis e PostgreSQL (apenas se optar por executar sem Docker)
- Opcional: Playwright (para etapas futuras de scraping com navegador)

### Arquivos de ambiente (.env)
- O projeto utiliza três arquivos de configuração:
  - `./.env.common` (raiz)
  - `market_alert/.env.market_alert`
  - `market_scraper/.env.market_scraper`
- Esses arquivos definem credenciais, URLs, chaves e parâmetros de scraping/observabilidade. Exemplos completos estão no `README.md:137` (``.env.common``), `README.md:168` (``.env.market_alert``) e `README.md:210` (``.env.market_scraper``).
- Carregamento: `shared/core/config_base.py` carrega `./.env.common` e, por serviço, o arquivo `.env.<serviço>`. Em Docker, a variável `ENV_FILE` já aponta para o arquivo correto de cada serviço.
- Boas práticas: não commitar segredos; use valores dummy em exemplos; evite imprimir variáveis sensíveis em logs.

### Subir stack com Docker Compose
- Tudo em segundo plano (inclui observabilidade):
  - `docker compose up -d --build`
- Somente dependências (para execução manual):
  - `docker compose up -d db redis redis-init`
- Serviços principais (API, Scraper, Worker, Beat):
  - `docker compose up -d api market_scraper celery-worker celery_beat`
- Observabilidade (separado, opcional):
  - `docker compose up -d prometheus alertmanager loki promtail grafana node-exporter cadvisor`
- Verificação rápida:
  - API health: `http://localhost:8000/health/ping`
  - API métricas: `http://localhost:8000/metrics`
  - Beat métricas: `http://localhost:8001/metrics`
  - Worker métricas: `http://localhost:8002/metrics`
  - Prometheus: `http://localhost:9090` | Grafana: `http://localhost:3000`

### Inicialização via Docker
- Subir dependências: `docker compose up -d db redis redis-init`
- Subir serviços principais: `docker compose up -d api market_scraper celery-worker celery_beat`
- Parar tudo: `docker compose down`

### Inicialização manual (desenvolvimento)
- Ambiente e deps (raiz):
  - Linux/macOS: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
  - Windows PowerShell: `python -m venv .venv; .venv/Scripts/Activate.ps1; pip install -r requirements.txt`
- Variáveis de ambiente:
  - `./.env.common`, `market_alert/.env.market_alert`, `market_scraper/.env.market_scraper`
  - Opcional: exportar `SERVICE_NAME=market_alert` ao rodar a API/worker e `SERVICE_NAME=market_scraper` ao rodar o scraper; ou definir `ENV_FILE` como no compose.
- Iniciar API: `uvicorn market_alert.main:app --port 8000 --reload`
- Iniciar Worker: `celery -A market_alert.core.celery_app:celery_app worker --loglevel=info --pool=threads --concurrency=4 -Q celery,scraping,monitor`
- Iniciar Beat: `python market_alert/beat_with_metrics.py`
- Iniciar Scraper: `uvicorn market_scraper.main:app --port 8010 --reload` (evita conflito local com métricas do Beat em 8001; use 8001 apenas se o Beat não estiver ativo)

#### Playwright (opcional)
- O projeto já inclui Playwright nas dependências, porém o uso de navegador headless está temporariamente desativado em produção.
- Para preparar o ambiente local e facilitar reativação futura:
  - `playwright install chromium` (após ativar a venv e instalar requirements)
- Diretrizes:
  - Mantenha a flag/estratégia de scraping configurada via `.env.market_scraper` (`SCRAPER_STRATEGIES`) e use headless conforme variáveis (`PLAYWRIGHT_HEADLESS`, `PLAYWRIGHT_TIMEOUT`).

### Tarefas Celery disponíveis
- collect_product_task(url: str, user_id: str, name_identification: str, target_price: float, monitored_id: str | None = None)
  - Função: coleta um produto monitorado e persiste no banco.
  - Efeitos: atualiza métricas; salva produto; registra erros de scraping quando necessário.
  - Observações: respeita flag de suspensão global via Redis.
- collect_competitor_task(monitored_product_id: str, url: str)
  - Função: coleta um concorrente, persiste e agenda `compare_prices_task`.
  - Efeitos: cria/atualiza concorrente; dispara comparação.
- compare_prices_task(monitored_id: str)
  - Função: compara preços do produto monitorado vs concorrentes.
  - Efeitos: pode acionar `send_notification_task(monitored_id, alerts)`; grava timestamp em Redis.
- send_notification_task(monitored_id: str, alerts: list)
  - Função: envia notificações conforme regras/canais ativos.
  - Efeitos: cria logs de envio e aplica supressões por cooldown/duplicidade.
- dispatch_price_alert_task(monitored_id: str, alert: dict)
  - Função: envia um único alerta específico.
- market_alert.tasks.monitor_tasks.recheck_monitored_products()
  - Função: rechecagem periódica de produtos monitorados; agenda comparação quando preço muda.
- market_alert.tasks.monitor_tasks.recheck_competitor_products()
  - Função: rechecagem periódica de concorrentes; agenda comparação quando preço muda.
- market_alert.tasks.metrics_tasks.*
  - collect_celery_metrics, collect_db_metrics, collect_audit_metrics, cleanup_cache (auxiliares/observabilidade).

> Preferência operacional: agende coletas via API HTTP (rotas abaixo) em vez de chamar tasks diretamente, evitando acoplamento.

### Exemplos de chamadas de API
- Autenticação (obter token JWT):
  - `POST /auth` (form-urlencoded)
  - Exemplo `curl`:
    - `curl -X POST http://localhost:8000/auth -H "Content-Type: application/x-www-form-urlencoded" -d "username=email@exemplo.com&password=SuaSenha"`
  - Resposta: `{ "access_token": "...", "token_type": "bearer" }`

- Agendar scraping de produto monitorado:
  - `POST /monitored/scrape`
  - Headers: `Authorization: Bearer <token>`; `Content-Type: application/json`
  - Body (JSON): `{ "name_identification": "Notebook XYZ", "product_url": "https://www.mercadolivre.com.br/MLB-...", "target_price": 3500.00 }`
  - Efeito: agenda `collect_product_task`; retorna 202 com mensagem de agendamento.

- Agendar scraping de concorrente:
  - `POST /competitors/scrape`
  - Headers: `Authorization: Bearer <token>`; `Content-Type: application/json`
  - Body (JSON): `{ "monitored_product_id": "<UUID-do-monitorado>", "product_url": "https://www.mercadolivre.com.br/MLB-..." }`
  - Efeito: agenda `collect_competitor_task`; retorna 202.

- Listar produtos monitorados e concorrentes:
  - `GET /monitored` → lista monitorados do usuário.
  - `GET /competitors/{monitored_product_id}` → lista concorrentes do monitorado.

- Rodar comparação manualmente:
  - `POST /comparisons/{monitored_id}/run?tolerance=0.01&price_change_threshold=0.02`
  - Headers: `Authorization: Bearer <token>`
  - Resposta: objeto de comparação com agregados; pode disparar notificações dependendo das regras.

- Chamada direta ao serviço de scraping (opcional, para testes):
  - `POST http://localhost:8001/parse`
  - Body (JSON): `{ "url": "https://www.mercadolivre.com.br/MLB-...", "product_type": "monitored" }`
  - Resposta: `{ "name": "...", "current_price": 1234.56, "marketplace": "..." }` ou `304 Not Modified`.

## Como Manter o AGENTS.md Atualizado

### O que fazer
- Revisar este documento a cada sprint ou nova versão, e sempre que houver mudanças relevantes de arquitetura/fluxos.
- Registrar imediatamente novos serviços, rotas de API, tarefas Celery, utilitários compartilhados, métricas/portas e variáveis de ambiente (incluindo como iniciar, dependências e integrações).
- Comparar o conteúdo com o `README.md` para evitar redundâncias: mantenha aqui instruções operacionais para agentes; no `README.md`, mantenha setup humano e visão geral.

> Nota: Um guia desatualizado prejudica a confiabilidade do agente e pode levar a ações incorretas (ex.: chamar endpoints removidos, agendar tarefas com parâmetros inválidos ou ignorar limites/portas atualizadas).

## Checklist de Cobertura Essencial

Use este checklist ao final de cada sprint/versão ou PR relevante para garantir cobertura. Quando a informação for extensa, referencie em vez de duplicar (ex.: `README.md`, `market_scraper/README.md`).

- [ ] Serviços e endpoints: nome, função, como iniciar, portas, dependências, principais rotas HTTP e endpoint `/metrics`.
- [ ] Tarefas Celery: lista de tasks com assinatura resumida, efeitos/efeitos colaterais, filas e quando são acionadas (API/Beat).
- [ ] Utilitários compartilhados: managers e helpers disponíveis (quando usar, principais responsabilidades) e onde estão no código.
- [ ] Métricas e observabilidade: métricas expostas por serviço, portas de scrape, jobs do Prometheus, SLOs/regras de alerta relevantes.
- [ ] Processos de teste: como rodar `pytest`, escopo preferido dos testes (parametrizados/próximos ao código), mocks/fixtures indispensáveis.
- [ ] Diretrizes de desenvolvimento: tipagem, docstrings, logging com `structlog`, instrumentação de métricas, compatibilidade de interfaces e política de migrações.
