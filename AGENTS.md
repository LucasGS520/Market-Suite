# AGENTS.md — Guia para Agentes de IA (Market Suite)

Este arquivo é um guia específico com instruções operacionais para agentes de IA que interagem com o código do projeto MarketSuite.
 Ele complementa os `README.md` voltado a pessoas desenvolvedoras, oferecendo contexto operacional do repositório, listagem de serviços e tarefas, utilidades internas e boas práticas destacando convenções internas, fluxos críticos, comandos frequentes e gatilhos de manutenção contínua.

> Nota: Sempre sincronize o conteúdo deste arquivo com o `README.md` e com os READMEs específicos dos serviços. Registre mudanças de arquitetura, novas filas, métricas ou variáveis assim que forem introduzidas.

## Objetivo
- Descrever como agentes de IA devem navegar no repositório e usar os serviços disponíveis.
- - Mapear os módulos ativos (`backend/` e `frontend/`) e apontar onde estão as responsabilidades de API, tarefas assíncronas, scraping e interface web.
- Fornecer atalhos para localizar documentação e código relevantes de cada serviço.
- Explicar rotinas essenciais (execução local, docker-compose, testes, migrações e observabilidade).
- Consolidar diretrizes de código, observabilidade, segurança e qualidade para que automações mantenham integridade entre serviços.

---

## Referências
## Referências imediatas
- `README.md`: visão geral da suíte, arquitetura e fluxos ponta a ponta.
- `backend/market_alert/README.md`: detalhes da API FastAPI, workers Celery e contratos de monitoramento.
- `backend/market_scraper/README.md`: responsabilidades do microserviço de scraping, pipeline de parsing e boas práticas.
- `frontend/README.md` (quando presente): convenções da aplicação React + Vite e instruções de build/deploy.

## Como Usar Este Documento
- Utilize este arquivo como manual operacional para automações, integrações entre serviços.
- Para visão conceitual, requisitos funcionais e setup humano consulte o `README.md` e, quando precisar de detalhes específicos, abra a documentação dos serviços correspondentes.

## Visão arquitetural rápida
- **Frontend (`frontend/`)**: aplicação React 18 servida por Vite, com servidor Express para produção. Consome a API pública e oferece dashboards responsivos.
- **Backend (`backend/`)**: agrega `market_alert` (API FastAPI, Celery Worker e Beat) e `market_scraper` (FastAPI dedicada a scraping). Recursos compartilhados ficam em `backend/shared/` (config, métricas, contratos Pydantic, clientes externos).
- **Infraestrutura de apoio**: PostgreSQL, Redis, Prometheus, Grafana, Loki e Alertmanager são orquestrados via `docker-compose.yml`.
- **Fluxo alto nível**: usuários interagem com o frontend → frontend chama a API `market_alert` → API agenda tarefas Celery → worker conversa com o `market_scraper`, Redis e PostgreSQL → eventos de domínio geram notificações persistidas → observabilidade coleta métricas/logs → dashboards são atualizados.

### Responsabilidades das tarefas Celery (`market_alert`)
- **Collector (`tasks.collector_product_task.collect_product_task`)**: processa uma URL por vez (monitorado ou concorrente), tenta obter lock no Redis e retorna um `ScrapeResult` padronizado (`success`, `not_modified`, `no_result`, `error`) contendo `http_status`, `price_changed`/`availability_changed` e `error_code` quando aplicável. Implementa retry automático com backoff exponencial (5s, 15s, 45s) via Celery countdown para erros temporários (timeout, 429, 5xx).
- **Agendador de rechecagem (`tasks.recheck_scheduler_task.schedule_rechecks`)**: Beat que varre `next_check_at` vencidos, atualiza o próximo horário calculado com **intervalo adaptativo** baseado em estabilidade de preço (5min a 2h) ou usa `check_interval` manual quando configurado, e enfileira a própria `collect_product_task` com jitter leve.
- **Intervalo Adaptativo**: produtos com preços estáveis são checados com menos frequência automaticamente. A lógica analisa o histórico de mudanças de preço e escala gradualmente: < 1h desde mudança = 5min, 1-6h = 5-30min, 6-24h = 30min-1h, > 24h = 2h. Isso reduz carga no sistema mantendo responsividade para produtos voláteis.
- **Comparação (`tasks.compare_prices_task.compare_prices_task`)**: idempotente e leve; usada pelo collector em cenários assíncronos e em acionamentos manuais para recalcular histórico/comparativos.
- **Notificações (`tasks.notifications_enqueue_task.enqueue_notifications_task`)**: normaliza notificações pendentes, calcula backoff exponencial e mantém consistência de retries antes de novos disparos.
- **Política de locks**: apenas o collector aplica o `acquire_product_lock` com TTL configurável via `PRODUCT_LOCK_TTL_SECONDS`, evitando flags em banco e mantendo TTL automático como único mecanismo de exclusão mútua.
- **Pausa de monitoramento**: monitorados com `paused=true` devem ser ignorados por agendador e collector, incrementando `monitored_skipped_paused` e mantendo histórico íntegro até retomada explícita.
- **Contratos de desfecho**: quando o lock não é adquirido o collector retorna `no_result` (mantendo métrica de lock skipped) para preservar o contrato enxuto; rechecagens sem mudança (`not_modified`) não geram novo `PriceHistory` e já atualizam `next_check_at`.
- **Retries não-bloqueantes**: o scraper client não realiza retries com `time.sleep()`. Erros temporários (timeout, 5xx, 429) são propagados para a task que agenda retry usando Celery `countdown`, evitando bloqueio do worker prefork.

## Diretrizes de Desenvolvimento para Agentes
- **Linguagem, Docstrings e comentários**: mantenha docstrings e comentários em português, descrevendo propósito, parâmetros, retornos e exceções. Evite comentários redundantes; foque em contexto e decisões. Siga esse padrão para comentários e Docstrings: (Ex: #Comentário Padrão vem seguido da Hastag, """ Docstrings possui espaço após incio e fim """).
- **Tipagem**: mantenha type hints em funções públicas e preserve compatibilidade adicionando parâmetros opcionais quando necessário.
- **Estrutura e estilo**: siga o padrão existente do repositório; não introduza linters/formatadores novos sem alinhamento. Evite `print`; utilize `structlog` e incremente métricas quando essencial e possível.
- **Testes**: crie ou ajuste testes com `pytest`. Execute `pytest -q` nos módulos afetados antes de concluir alterações.
- **Métricas**: ao criar fluxos relevantes, exponha contadores/histogramas e reutilize nomes/padrões já existentes.
- **Workers Celery**: utilize pool `prefork` ao subir workers (`celery -A market_alert.core.celery_app worker -P prefork ...`) para que `time.sleep` em backoffs não bloqueie pools cooperativos. Para notificações, mantenha um worker dedicado consumindo a fila `notifications`. Caso migre de pool, substitua esperas bloqueantes por `countdown` ou sleeps compatíveis.
- **Pesquisa no código**: prefira `rg` (ripgrep) para buscas rápidas; se indisponível, use `grep -Rni` com exclusões de diretórios (`.venv`, `.git`, caches). Exemplos: `rg -n "metrics|/metrics"`, `rg -n "collect_.*_task" market_alert`.
- **Commits**: mantenha mensagens claras no formato `<tipo>: <resumo>` do tipo de mudança (ex.: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`), sempre traga a frase utilizada para o commit ao final da resposta (Ex: feat: Add nova instrução ao AGENTS.md). Faça mudanças pequenas e coesas; referência arquivos/rotas afetadas. Evite criar branches sem necessidade ou renomear arquivos amplamente.
- **Orquestração de scraping**: use sempre a task central `market_alert.tasks.collector_product_task.collect_product_task` e o serviço `services/collector_service_orchestrator.py` para enfileirar monitorados e concorrentes. Evite chamadas diretas ao scraper; as rechecagens periódicas passam pelo agendador `tasks.recheck_scheduler_task.schedule_rechecks`, que enfileira diretamente na fila `scraping`.
- **Alterações de interface**: evite quebras em contratos de API, schemas Pydantic ou assinaturas de tasks Celery. Preserve retrocompatibilidade e documente qualquer deprecação. e atualize `AGENTS.md`, `README.md` e testes.
- **Banco e migrações**: alterações de schema devem passar por Alembic; nunca execute deleções em massa sem salvaguardas.
- **Observabilidade**: registre logs estruturados, atualize métricas e revise Prometheus quando necessário.
- **Segurança**: não exponha segredos. Utilize arquivos `.env` e helpers para acessar configurações.
- **Compatibilidade local/Docker**: mantenha portas alinhadas ao `docker-compose.yml`; evite conflitos.
- **Manutenção documental**: ao final de cada sprint ou mudança estrutural, sinalize ou execute atualizações necessárias em `README.md` e `AGENTS.md`.
- **Scraper**: a inferência de disponibilidade ocorre antes do validador e deve propagar `last_status` em ordem de precedência (payload > inferência > validador). A rota `GET /monitored/` lista itens sem preço para indicar indisponibilidade.

## Interação entre serviços
- Comunicação frontend ⇄ backend via HTTP/JSON. O cliente padrão (`frontend/src/lib/api.ts`) injeta JWT no header `Authorization` e tenta renovar a sessão via `/auth/refresh` quando recebe `401`.
- A tela `/settings` consome endpoints protegidos `/settings`, `/settings/profile` e `/settings/notifications`, separando preferências persistidas (perfil/canais) de ajustes visuais locais.
- Workers Celery consomem filas `celery`, `scraping`, `monitor` e `notifications`, armazenando resultados no PostgreSQL, reprocessando comparações e enfileirando entregas de alertas.
- O `ScraperClient` (`backend/market_alert/services/scraper_client.py`) envia requisições `POST /scraper/parse` ao `market_scraper`, que executa pipeline `FetchHTML → DomainSpecificParser → JsonLdParser → HtmlMetadataParser → GenericFallbackParser`.
- Resultados de scraping são persistidos e utilizados para calcular difusão de preços e atualizar dashboards.

### Autenticação e verificação
- O login (`POST /auth/login`) retorna `access_token`/`refresh_token` e também define cookie HttpOnly para refresh com `SameSite=None` e `Path=/` por padrão.
- O refresh (`POST /auth/refresh`) aceita refresh token via cookie HttpOnly (payload JSON opcional apenas como fallback).
- O logout (`POST /auth/logout`) revoga o refresh token e remove o cookie HttpOnly quando presente.
- Verificações: `POST /auth/verify-email?token=...` e `POST /auth/verify-phone` com `{ user_id, otp }`.
- Reenvio: `POST /users/resend-verification` com `{ channel: "email" | "phone_number" }`, respeitando cooldown do backend.
- Métricas de verificação ficam em `backend/shared/metrics/metrics_auth.py` (`verification_sent_total`, `verification_resend_attempts_total`, `verification_success_total`, `verification_failure_total`).

### Arquivos de ambiente (.env)
- O projeto utiliza três arquivos de configuração no `backend`:
  - `backend/.env.common` (raiz)
  - `backend/market_alert/.env.market_alert`
  - `backend/market_scraper/.env.market_scraper`
Carregamento: `backend/shared/core/config_base.py` carrega `./.env.common` e, por serviço, o arquivo `.env.<serviço>`.
- No `frontend` existe apenas um arquivo de configuração:
  - `frontend/.env`
 Em Docker, a variável `ENV_FILE` já aponta para o arquivo correto de cada serviço.
- Boas práticas: não commitar segredos; use valores dummy em exemplos; evite imprimir variáveis sensíveis em logs.
- Auth cookies: em HTTP local com frontend em outro host/porta, ajuste `REFRESH_TOKEN_COOKIE_SECURE=0` e `REFRESH_TOKEN_COOKIE_SAMESITE=none`.
- CORS: declare `FRONTEND_ORIGINS` com a lista de origens permitidas (separadas por vírgula) para chamadas do frontend com cookies.

## Testes e qualidade
- Backend: `pytest backend/market_alert -q`, `pytest backend/market_scraper -q` e demais testes em `backend/shared/tests`.
- Frontend: `pnpm test` (quando configurado) e `pnpm lint`.
- Valide comandos em ambientes isolados e registre no relatório final as execuções realizadas.

## Checklist antes de concluir uma mudança
1. Atualize ou confirme a existência de docstrings/comentários relevantes em português.
2. Ajuste contratos, schemas ou métricas conforme necessário e estejam bem sincronizados com o projeto geral.
3. Execute testes pertinentes e registre resultados.
4. Valide se novas portas/variáveis foram documentadas.
5. Revise o `README.md` e demais READMEs específicos para garantir consistência.
6. Confirme que contratos críticos consumidos pelo frontend permanecem coerentes.

## Manutenção contínua - AGENTS.md Atualizado
- Revisar este documento a cada sprint ou nova versão, e sempre que for realizado novas tarefas e mudanças no projeto.
- Documentar mudanças relevantes sempre que atualizar fluxos de autenticação, scraping, comparação, observabilidade ou arquitetura.
- Adicionar instruções sobre novos serviços, filas, métricas, variáveis de ambiente, pipelines ou convenções.
- Remover comandos desatualizados e alinhar com os READMEs específicos.
- Comparar o conteúdo com o `README.md` para evitar redundâncias: mantenha aqui instruções operacionais para agentes; no `README.md`, mantenha setup humano e visão geral.

> Nota: Um guia desatualizado prejudica a confiabilidade do agente e pode levar a ações incorretas.

## Estabilidade do MVP - Melhorias Implementadas

### Eliminação de Bloqueios em Workers (Janeiro 2026)
**Problema:** Chamadas `time.sleep()` no scraper client bloqueavam workers Celery prefork durante retries, reduzindo throughput.
**Solução:** Removido loop de retry com sleep do scraper client. Retries agora gerenciados pela task Celery usando `countdown` (5s, 15s, 45s backoff exponencial).
**Impacto:** Workers mantêm disponibilidade durante retries, melhorando capacidade de processamento paralelo.

### Limitação de Loops Infinitos (Janeiro 2026)
**Problema:** Task de limpeza de cache Redis (`cleanup_cache`) executava `while True` sem timeout, podendo bloquear por minutos em bases grandes.
**Solução:** Adicionados limites de segurança: máximo 10.000 iterações e timeout de 60 segundos.
**Impacto:** Previne bloqueios prolongados mantendo funcionalidade de limpeza eficaz.

### Agendamento Adaptativo (Janeiro 2026)
**Problema:** Todos os produtos checados a cada 5 minutos independente de estabilidade, gerando carga desnecessária.
**Solução:** Implementado escalonamento automático baseado em histórico de mudanças de preço:
- Produtos voláteis (mudança < 1h): checados a cada 5 minutos
- Estabilizando (1-6h): escala gradual até 30 minutos
- Estáveis (6-24h): escala gradual até 1 hora
- Muito estáveis (> 24h): checados a cada 2 horas
**Impacto:** Redução estimada de 60-80% em chamadas de scraping para produtos estáveis, liberando capacidade para produtos críticos.

### Validação de Configuração (Janeiro 2026)
**Problema:** Timeouts misconfigured causavam falhas silenciosas em runtime.
**Solução:** Validação na inicialização do Settings, com UserWarning e auto-correção quando `SCRAPER_TOTAL_TIMEOUT < SCRAPER_CONNECT_TIMEOUT + SCRAPER_READ_TIMEOUT`.
**Impacto:** Falhas detectadas no startup com orientação clara para correção no `.env`.

### Métricas de Observabilidade
Novas métricas Prometheus para monitoramento do comportamento adaptativo:
- `adaptive_interval_calculated_seconds`: histograma de intervalos calculados
- `adaptive_interval_decision_total{category}`: contador de decisões por categoria
- Categorias: `no_scrape_history`, `no_price_history`, `recent_change`, `scaling_6h`, `scaling_24h`, `stable_24h_plus`, `error_fallback`

### Boas Práticas para Manutenção
- **Nunca usar `time.sleep()` em tasks Celery**: use `countdown` ou `apply_async(eta=...)` para delays não-bloqueantes
- **Sempre limitar loops**: adicione timeouts e/ou limites de iteração em qualquer `while True`
- **Validar configurações críticas**: adicione validação no `__init__` de Settings para falhar rápido
- **Expor métricas**: toda decisão de sistema deve ter métrica correspondente para observabilidade
- **Testar sob carga**: validar comportamento com volumes realistas antes de produção
