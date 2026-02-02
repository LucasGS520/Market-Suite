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
- **Backend (`backend/`)**: agrega `market_alert` (API FastAPI + 4 Workers Celery dedicados) e `market_scraper` (FastAPI dedicada a scraping). Recursos compartilhados ficam em `backend/shared/` (config, métricas, contratos Pydantic, clientes externos).
- **Infraestrutura de apoio**: PostgreSQL, Redis, Prometheus, Grafana, Loki e Alertmanager são orquestrados via `docker-compose.yml`.
- **Fluxo alto nível**: usuários interagem com o frontend → frontend chama a API `market_alert` → API agenda tarefas Celery em filas específicas → workers dedicados consomem e processam → scraper coleta dados → eventos de domínio geram notificações → observabilidade coleta métricas/logs → dashboards são atualizados.
- **Agendamento contínuo**: o worker `celery-worker-monitor` executa indefinidamente `run_continuous_collector`, que consome a fila de prioridade Redis (sorted sets), dispara coletas assíncronas de monitorados + concorrentes na fila `scraping` e mantém o reenqueue pendente até a coleta finalizar.

### Responsabilidades das tarefas Celery (`market_alert`) e Organização de Workers

**Workers Celery:**
- **celery-worker-scraping** (fila `celery,scraping`, concorrência 4): executa `collect_product_task` para scraping imediato de um monitorado/concorrente por vez.
- **celery-worker-monitor** (fila `monitor`, concorrência 4): executa o loop contínuo `run_continuous_collector`.
- **celery-worker-compare** (fila `compare`, concorrência 2): executa `compare_prices_task` após coletas com mudanças.
- **celery-worker-notifications** (fila `notifications`, concorrência 2): executa `send_notification_task` + `verification_tasks`.

**Tasks principais:**
- **Collector (`tasks.collector_product_task.collect_product_task`, fila `scraping`)**: processa uma URL por vez (monitorado ou concorrente), tenta obter lock Redis e retorna `ScrapeResult` padronizado (`success`, `not_modified`, `no_result`, `error`).
- **Coletor contínuo (`tasks.continuous_collector_task.run_continuous_collector`, fila `monitor`)**: **task que roda indefinidamente** no worker-monitor, consome a fila de prioridade Redis (sorted sets), despacha monitorado + concorrentes para a fila `scraping` e mantém o item em processamento até a coleta terminar. Inicia via `CONTINUOUS_COLLECTOR_AUTOSTART=1`.
- **Comparação (`tasks.compare_prices_task.compare_prices_task`, fila `compare`)**: idempotente e leve; disparada automaticamente após coletas com mudanças de preço/disponibilidade.
- **Notificações (`tasks.send_notification_task.send_notification_task`, fila `notifications`)**: entrega alertas com retry e backoff exponencial, registra em `notification_attempt`.

**Política de locks**: apenas o collector aplica o `acquire_product_lock` com TTL configurável via `PRODUCT_LOCK_TTL_SECONDS`, evitando race conditions e usando Redis como único mecanismo de exclusão mútua (sem flags em banco).

**Pausa de monitoramento**: monitorados com `paused=true` são ignorados por collector e loop contínuo, incrementando `monitored_skipped_paused` e mantendo histórico íntegro até retomada explícita.

**Contratos de desfecho**: quando lock não é adquirido, collector retorna `no_result` com métrica `lock_skipped`; respostas `not_modified` não geram novo `PriceHistory` e atualizam apenas `last_checked`.

## Diretrizes de Desenvolvimento para Agentes
- **Linguagem, Docstrings e comentários**: mantenha docstrings e comentários em português, descrevendo propósito, parâmetros, retornos e exceções. Evite comentários redundantes; foque em contexto e decisões. Siga esse padrão para comentários e Docstrings: (Ex: #Comentário Padrão vem seguido da Hastag, """ Docstrings possui espaço após incio e fim """).
- **Tipagem**: mantenha type hints em funções públicas e preserve compatibilidade adicionando parâmetros opcionais quando necessário.
- **Estrutura e estilo**: siga o padrão existente do repositório; não introduza linters/formatadores novos sem alinhamento. Evite `print`; utilize `structlog` e incremente métricas quando essencial e possível.
- **Testes**: crie ou ajuste testes com `pytest`. Execute `pytest -q` nos módulos afetados antes de concluir alterações.
- **Métricas**: ao criar fluxos relevantes, exponha contadores/histogramas e reutilize nomes/padrões já existentes.
- **Workers Celery**: utilize pool `prefork` ao subir workers (`celery -A market_alert.core.celery_app worker -P prefork ...`) para que `time.sleep` em backoffs não bloqueie pools cooperativos. Para notificações, mantenha um worker dedicado consumindo a fila `notifications`. Caso migre de pool, substitua esperas bloqueantes por `countdown` ou sleeps compatíveis.
- **Pesquisa no código**: prefira `rg` (ripgrep) para buscas rápidas; se indisponível, use `grep -Rni` com exclusões de diretórios (`.venv`, `.git`, caches). Exemplos: `rg -n "metrics|/metrics"`, `rg -n "collect_.*_task" market_alert`.
- **Commits**: mantenha mensagens claras no formato `<tipo>: <resumo>` do tipo de mudança (ex.: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`), sempre traga a frase utilizada para o commit ao final da resposta (Ex: feat: Add nova instrução ao AGENTS.md). Faça mudanças pequenas e coesas; referência arquivos/rotas afetadas. Evite criar branches sem necessidade ou renomear arquivos amplamente.
- **Orquestração de scraping**: use sempre a task central `market_alert.tasks.collector_product_task.collect_product_task` que será enfileirada na fila `scraping`. O worker `celery-worker-monitor` consome a fila de prioridade Redis e dispara coletas via `collect_product_task` automaticamente. Evite chamadas diretas ao scraper; o padrão orquestrador centraliza tudo.
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
- Workers Celery consomem filas `celery`, `scraping`, `monitor`, `compare` e `notifications`, armazenando resultados no PostgreSQL, reprocessando comparações e enfileirando entregas de alertas.
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

## Troubleshooting do coletor contínuo
- **Fila vazia ou sem itens prontos**: verifique `PRIORITY_QUEUE_SIZE`, `PRIORITY_QUEUE_READY_TOTAL` e o conjunto ordenado configurado em `PRIORITY_QUEUE_KEY`. Garanta que o monitorado foi enfileirado com `next_check_at` válido e que não está preso em processamento aguardando requeue pós-coleta.
- **Worker monitor inativo**: confirme o processo `celery-worker-monitor` ativo e a env `CONTINUOUS_COLLECTOR_AUTOSTART=1`. Sem ela, o loop não inicia automaticamente.
- **Redis indisponível**: valide conectividade e credenciais; o coletor registra `continuous_queue_unavailable` quando o Redis não responde.
- **Itens presos em processamento**: o loop reaproveita o conjunto de processamento após o TTL configurado em `CONTINUOUS_WORKER_PROCESSING_TTL_SECONDS`. Verifique logs de `continuous_processing_reclaimed` e a métrica `priority_queue_pending_requeue_total`.
- **Monitorados pausados**: itens com `paused=true` são ignorados e não retornam para a fila; retome manualmente para reativar a coleta.

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

## Manutenção contínua - AGENTS.md Atualizado
- Revisar este documento a cada sprint ou nova versão, e sempre que for realizado novas tarefas e mudanças no projeto.
- Documentar mudanças relevantes sempre que atualizar fluxos de autenticação, scraping, comparação, observabilidade ou arquitetura.
- Adicionar instruções sobre novos serviços, filas, métricas, variáveis de ambiente, pipelines ou convenções.
- Remover comandos desatualizados e alinhar com os READMEs específicos.
- Comparar o conteúdo com o `README.md` para evitar redundâncias: mantenha aqui instruções operacionais para agentes; no `README.md`, mantenha setup humano e visão geral.

> Nota: Um guia desatualizado prejudica a confiabilidade do agente e pode levar a ações incorretas.
