# Market Alert
Servico FastAPI responsável por orquestrar monitoramento de precos, persistir usuarios/produtos/comparacoes/notificacoes e executar workflows assincronos de coleta e entrega. O modulo expoe API REST para operacoes sincronas e utiliza Celery + Redis para filas, retries, locks e tarefas de longa duracao. O `market_scraper` e consumido via HTTP para parsing de URLs; o `market_alert` concentra estado, regras de negocio e distribuicao de alertas.

## Relacoes e Referências
- Visao arquitetural da suite: [`../README.md`](../README.md)
- Servico de scraping consumido pela API: [`../market_scraper/README.md`](../market_scraper/README.md)
- Guia operacional para agentes: [`../AGENTS.md`](../AGENTS.md)

## Principais Responsabilidades
- **Expor a API principal do sistema** com CORS, rate limiting, autenticacao JWT e health checks.
- **Persistir estado de negocio em PostgreSQL** (usuarios, produtos, historico de precos, comparacoes, tokens, notificacoes e erros de tarefa).
- **Orquestrar tarefas** assincronas com Celery, filas dedicadas por dominio e agendamentos periodicos.
- **Integração com o `market_scraper`** para transformar URLs monitoradas em snapshots normalizados de mercado.

## Estrutura do Diretório
```text
market_alert/
|-- auth/                      # Autenticacao, refresh token, logout, perfil e reset de senha
|-- users/                     # Contas, identidade, configuracoes e verificacoes
|-- products/                  # Produtos monitorados, concorrentes, dashboard e lifecycle
|-- collectors/                # Orquestracao de coleta, filas, locks e integracao com scraper
|-- comparisons/               # Calculo e consulta de comparacoes de preco
|-- notifications/             # Avaliacao, renderizacao e entrega de notificacoes
|-- core/                      # Configuracao do servico e utilitarios centrais de seguranca
|-- infraestructure/           # Logging, health, Celery, resilience e bootstrap operacional
|-- models/                    # Modelos ORM persistidos no PostgreSQL
|-- schemas/                   # Contratos Pydantic de request/response
|-- enums/                     # Enumeracoes de dominio
|-- scraper/                   # Cliente HTTP oficial do market_scraper
|-- alembic/                   # Migracoes de banco de dados
|-- tests/                     # Suite de testes unitarios e de integracao
└── main.py                    # Entry point da aplicacao FastAPI
```

---

## Endpoints e Fluxos HTTP
As rotas publicas sao registradas em [`main.py`](main.py) e divididas por dominio. Abaixo estao os endpoints atualmente expostos pela API, com foco no contrato HTTP e na responsabilidade principal de cada entrada.

### Fluxos HTTP mais relevantes
- Cadastro e onboarding: `POST /users/` cria a conta em estado pendente e dispara verificacoes de email/telefone na fila `notifications`.
- Sessao autenticada: `POST /auth/login` emite JWT para o header `Authorization` e refresh token para cookie HttpOnly (ou payload compativel).
- Configuracao do usuario: `/settings` e `/notifications/preferences` separam preferencias globais de canal das preferencias especificas por tipo de alerta.
- Monitoramento: `POST /monitored/scrape` e `POST /competitors/scrape` devolvem `202 Accepted`, pois a coleta real e assincrona e prossegue via Celery.
- Consulta operacional: `/monitored`, `/competitors`, `/comparisons/*` e `/notifications/` expoem o estado persistido e os agregados consumidos pelo frontend.

## Dominios e Componentes Chave

### Auth
- O pacote [`auth/`](auth/) concentra autenticacao de sessao, rotacao de refresh token, logout e fluxos de verificacao/reset de credenciais.
- [`auth/services/services_auth.py`](auth/services/services_auth.py) organiza login, emissao de JWT, refresh token, logout, troca de email/senha e confirmacao de tokens de verificacao.
- O login aplica bloqueio por IP e contagem de falhas via [`infraestructure/security/bruteforce.py`](infraestructure/security/bruteforce.py), reduzindo risco de brute force.
- O refresh token pode ser recebido por payload ou cookie HttpOnly; [`auth/utils/cookies_auth.py`](auth/utils/cookies_auth.py) centraliza `Secure`, `SameSite`, `Path` e limpeza do cookie.
- O conjunto de rotas em `auth/routes_auth/` esta separado por caso de uso: `login`, `refresh`, `logout`, `profile`, `reset_password` e `verify`.

#### Endpoints - Autenticacao e Perfil
| Metodo | Rota | Contrato principal | Responsabilidade |
|--------|------|--------------------|------------------|
| `POST` | `/auth/login` | `OAuth2PasswordRequestForm` -> `TokenPairResponse` | Autentica o usuario, aplica protecao contra brute force e retorna `access_token` + `refresh_token`. |
| `POST` | `/auth/refresh` | `RefreshRequest` opcional -> `TokenPairResponse` | Rotaciona refresh token via payload ou cookie HttpOnly e emite novo par de tokens. |
| `POST` | `/auth/logout` | `RefreshRequest` opcional -> `204 No Content` | Revoga o refresh token atual e remove o cookie de sessao. |
| `POST` | `/auth/verify-email` | `token` via query -> mensagem simples | Consome token de verificacao de email e confirma o fator. |
| `POST` | `/auth/verify-phone` | `PhoneOtpRequest` -> mensagem simples | Valida OTP de telefone e conclui verificacao do numero. |
| `POST` | `/auth/reset_password/request` | `ResetPasswordRequest` -> mensagem simples | Inicia o fluxo de reset de senha gerando token de recuperacao. |
| `POST` | `/auth/reset_password/confirm` | `ResetPasswordConfirmRequest` -> mensagem simples | Confirma token de reset e atualiza a senha do usuario. |
| `POST` | `/auth/change-password` | `ChangePasswordRequest` -> mensagem simples | Permite troca de senha para usuario autenticado. |
| `POST` | `/auth/change-email` | `ChangeEmailRequest` -> mensagem simples | Altera email e invalida a verificacao anterior do endereco. |

### Users
- O pacote [`users/`](users/) cobre cadastro, administracao de contas, verificacao de identidade e configuracoes do usuario.
- [`users/services/services_account.py`](users/services/services_account.py) registra usuarios pendentes, aplica rate limit por IP de cadastro e dispara tarefas de verificacao de email/telefone.
- [`users/services/services_identity.py`](users/services/services_identity.py) consome tokens/OTPs, reenvia verificacoes com cooldown e promove contas `pending` para `active` quando os fatores exigidos foram confirmados.
- [`users/services/services_settings.py`](users/services/services_settings.py) consolida perfil e preferencias de notificacao, invalida verificacoes ao trocar email/telefone e dispara novas confirmacoes quando necessario.
- [`users/tasks/verification_tasks.py`](users/tasks/verification_tasks.py) envia email de verificacao e OTP por SMS na fila `notifications`, mantendo o fluxo assincrono fora da request HTTP.

#### Endpoints - Usuarios e Configuracões
| Metodo | Rota | Contrato principal | Responsabilidade |
|--------|------|--------------------|------------------|
| `POST` | `/users/` | `UserCreate` -> `UserResponse` | Cadastra usuario, normaliza contatos e dispara verificacoes iniciais. |
| `PUT` | `/users/{user_id}/status` | query `active: bool` -> `UserResponse` | Ativa ou suspende conta alvo; rota restrita a administradores. |
| `PUT` | `/users/{user_id}` | `UserUpdate` -> `UserResponse` | Atualiza dados administrativos do usuario; rota restrita a administradores. |
| `GET` | `/users/me` | autenticado -> `UserResponse` | Retorna o perfil bruto do usuario autenticado. |
| `POST` | `/users/resend-verification` | `VerificationResendRequest` -> mensagem simples | Reenvia token/OTP de verificacao com rate limit e cooldown. |
| `GET` | `/settings` | autenticado -> `SettingsOverviewResponse` | Retorna resumo agregado de perfil + preferencias para a tela de configuracoes. |
| `GET` | `/settings/profile` | autenticado -> `SettingsProfileResponse` | Retorna os dados de perfil usados na tela de configuracoes. |
| `PATCH` | `/settings/profile` | `SettingsProfileUpdate` -> `SettingsProfileUpdateResponse` | Atualiza perfil e sinaliza se novas verificacoes de email/telefone foram exigidas. |
| `GET` | `/settings/notifications` | autenticado -> `NotificationSettings` | Retorna preferencias globais de canais de notificacao. |
| `PATCH` | `/settings/notifications` | `NotificationSettings` -> `NotificationSettings` | Atualiza preferencias globais de email/push/sms/whatsapp. |

### Products
- O pacote [`products/`](products/) gerencia o ciclo de vida de produtos monitorados e concorrentes, alem das consultas usadas pelo dashboard.
- [`products/services/services_monitored.py`](products/services/services_monitored.py) e [`products/services/services_competitors.py`](products/services/services_competitors.py) sao camadas read-only para listagem, paginacao e montagem dos DTOs retornados pela API.
- [`products/services/services_monitored_lifecycle.py`](products/services/services_monitored_lifecycle.py) cria, pausa, retoma e remove monitorados, validando URL, duplicidade, rate limit, lock Redis e sincronizacao com a fila de coleta continua.
- [`products/services/services_competitor_lifecycle.py`](products/services/services_competitor_lifecycle.py) cria e remove concorrentes, impede auto-referencia, respeita limite maximo por monitorado e agenda recaptura/comparacao apos mudancas.
- [`products/services/services_access_control.py`](products/services/services_access_control.py) garante ownership por usuario antes de expor ou alterar um monitorado.
- [`products/domain/product_lifecycle.py`](products/domain/product_lifecycle.py) concentra regras puras de transicao de status, rastreio de mudanca de preco e calculo do proximo `next_check_at`.
- [`products/domain/stability.py`](products/domain/stability.py) reexporta a politica de estabilidade usada para acelerar ou desacelerar o monitoramento continuo conforme variacao observada.

### Collectors
- O pacote [`collectors/`](collectors/) e a camada de orquestracao de coleta: recebe pedidos de scraping, monta payloads, aplica locks e gerencia a fila continua.
- [`collectors/orchestrator/collector_service_orchestrator.py`](collectors/orchestrator/collector_service_orchestrator.py) encapsula o enfileiramento de monitorados e concorrentes na `collect_product_task`, incluindo batching e jitter para concorrentes.
- [`collectors/tasks/collector_product_task.py`](collectors/tasks/collector_product_task.py) e a task unitaria de scraping: valida payload, aplica lock Redis por produto, delega para o service correto e agenda recomputacao de comparacoes apos commit.
- [`collectors/domain/collection_queue.py`](collectors/domain/collection_queue.py) abstrai a fila de prioridade Redis (`queue` + `processing`) com operacoes de enqueue, pop, reclaim e remocao.
- [`collectors/services/continuous_collector_manager.py`](collectors/services/continuous_collector_manager.py) executa o loop continuo, garante singleton via lock Redis, revalida autostart e reencaminha itens presos em processamento.
- [`collectors/domain/collection_reconciliation.py`](collectors/domain/collection_reconciliation.py) reconcilia a fila Redis com os monitorados ativos persistidos no banco, reduzindo perdas apos restart ou falhas.

#### Endpoints - Produtos, Dashboard e Concorrentes
| Metodo | Rota | Contrato principal | Responsabilidade |
|--------|------|--------------------|------------------|
| `GET` | `/dashboard/stats` | autenticado -> `dict[str, int]` | Retorna totais exibidos no dashboard (`total_monitored`, `total_competitors`, `ok_prices`). |
| `POST` | `/monitored/scrape` | `MonitoredProductCreateScraping` -> `MonitoredScrapeCreationResponse` (`202`) | Cria monitorado pendente, valida URL e enfileira coleta inicial. |
| `GET` | `/monitored` | query `page`, `per_page`, `query`, `status` -> `PaginatedMonitoredProductsResponse` | Lista monitorados com filtros textuais e de competitividade. |
| `GET` | `/monitored/featured` | autenticado -> `list[MonitoredProductResponse]` | Retorna monitorados destacados para cards do dashboard. |
| `GET` | `/monitored/{product_id}` | autenticado -> `MonitoredProductResponse` | Retorna detalhe consolidado de um monitorado. |
| `PUT` | `/monitored/{product_id}/paused` | query `paused: bool` -> `MonitoredProductResponse` | Pausa ou retoma o monitoramento, sincronizando a fila continua. |
| `DELETE` | `/monitored/{product_id}` | autenticado -> `{success, product_id}` | Remove monitorado, limpa locks e fila de prioridade. |
| `POST` | `/competitors/scrape` | `CompetitorProductCreateScraping` -> `CompetitorScrapeCreationResponse` (`202`) | Cria concorrente pendente e agenda coleta inicial. |
| `GET` | `/competitors` | query `monitored_id`, `page`, `per_page`, `include_inactive`, `include_paused` -> `CompetitorsListResponse` | Lista concorrentes de um monitorado com contadores e paginacao. |
| `DELETE` | `/competitors/{competitor_id}` | autenticado -> `{success, competitor_id}` | Remove concorrente e dispara recomputacao de comparacao do monitorado. |

### Comparisons
- O pacote [`comparisons/`](comparisons/) transforma snapshots de monitorado e concorrentes em comparacoes persistidas e resumos competitivos reutilizaveis pelo frontend.
- [`comparisons/services/services_comparison.py`](comparisons/services/services_comparison.py) e o ponto de entrada da orquestracao: carrega dados, valida ownership para consultas HTTP, executa comparacao e persiste `PriceComparison` + `PriceComparisonSummary`.
- [`comparisons/services/services_comparison_calculator.py`](comparisons/services/services_comparison_calculator.py) concentra calculos puros e recomposicao de resumo: ranking, media, menor/maior preco, `potential_adjustment`, status competitivo e texto de insight.
- [`comparisons/domain/price_competitiveness.py`](comparisons/domain/price_competitiveness.py) define os limiares configuraveis de competitividade e a classificacao `competitive` / `attention` / `urgent`.
- [`comparisons/utils/price_comparator.py`](comparisons/utils/price_comparator.py) calcula discrepancias por concorrente e tambem centraliza o debounce de reprocessamento assinado por Redis.
- [`comparisons/tasks/compare_prices_task.py`](comparisons/tasks/compare_prices_task.py) roda na fila `compare`, persiste o resumo e aciona a avaliacao de notificacoes apenas quando faz sentido operacionalmente.

### Notifications
- O pacote [`notifications/`](notifications/) avalia eventos, renderiza mensagens, persiste historico de entregas e envia alertas por multiplos canais.
- [`notifications/evaluator.py`](notifications/evaluator.py) e um avaliador stateless: detecta eventos a partir de snapshots, cruza preferencias/regras, resolve canal/destinatario e produz `NotificationCandidate`.
- [`notifications/services/services_notifications.py`](notifications/services/services_notifications.py) e o orchestrator principal: aplica deduplicacao, cooldown, locks, cria `event_log` e `notification`, enfileira pendentes e processa envios com retry/dead-letter.
- [`notifications/template_renderer.py`](notifications/template_renderer.py) renderiza templates Jinja2 por canal (`email`, `sms`, `whatsapp`, `push`, `webhook`) com fallback para templates genericos.
- O subpacote [`notifications/domain/`](notifications/domain/) contem regras puras como deteccao de eventos, resolucao de prioridade/cooldown, validacao de snapshot e resolucao de canais confirmados.
- O subpacote [`notifications/infra/channels/`](notifications/infra/channels/) isola adapters de entrega, permitindo trocar providers sem contaminar a camada de dominio.
- [`notifications/tasks/notifications_enqueue_task.py`](notifications/tasks/notifications_enqueue_task.py) e [`notifications/tasks/send_notification_task.py`](notifications/tasks/send_notification_task.py) separam descoberta de pendencias e envio efetivo por canal.

#### Endpoints - Comparacoes e Notificacoes
| Metodo | Rota | Contrato principal | Responsabilidade |
|--------|------|--------------------|------------------|
| `GET` | `/comparisons/{monitored_id}` | query `page`, `per_page` -> `PaginatedPriceComparisonResponse` | Lista historico paginado de comparacoes para um monitorado. |
| `GET` | `/comparisons/{monitored_id}/summary` | autenticado -> `PriceComparisonSummaryResponse` | Retorna o resumo mais recente, recomposto se o snapshot estiver defasado. |
| `GET` | `/comparisons/detail/{comparison_id}` | autenticado -> `PriceComparisonResponse` | Retorna o registro detalhado de uma comparacao especifica. |
| `GET` | `/notifications/` | query `page`, `per_page` -> `PaginatedNotificationResponse` | Lista notificacoes persistidas para o usuario autenticado. |
| `GET` | `/notifications/preferences` | autenticado -> `list[UserNotificationPreferenceResponse]` | Retorna preferencias de notificacao por canal e tipo de alerta. |
| `POST` | `/notifications/preferences` | `UserNotificationPreferenceCreate` -> `UserNotificationPreferenceResponse` (`201`) | Cria ou atualiza uma preferencia especifica de notificacao. |

### Seguranca Compartilhada
- [`infraestructure/security/auth_context.py`](infraestructure/security/auth_context.py) valida JWT bearer, resolve o usuario corrente e restringe rotas administrativas.
- [`core/jwt.py`](core/jwt.py) cria e valida access tokens assinados com `SECRET_KEY` e `ALGORITHM`, incluindo `sub`, `jti`, claims de verificacao e exp.
- [`core/password.py`](core/password.py) centraliza hashing/verificacao com `bcrypt`.
- [`core/tokens.py`](core/tokens.py) gera tokens de verificacao, tokens de reset, OTP telefonico, hash de token e calculo de expiracao.

### Contratos e Enumeracoes
- O pacote [`schemas/`](schemas/) define os contratos Pydantic de entrada/saida por dominio: autenticacao (`schemas_auth.py`), usuarios (`schemas_users.py`), configuracoes (`schemas_settings.py`), produtos (`schemas_products.py`), comparacoes (`schemas_comparisons.py`), notificacoes (`schemas_notifications.py`) e payload de coleta (`schemas_collection_payload.py`).
- O pacote [`enums/`](enums/) concentra estados e classificacoes compartilhadas: status de usuario e verificacao, estados de produto, status de competitividade, tipos de evento/alerta, canais de notificacao e estados de entrega.
- Esses contratos estabilizam a fronteira entre API, tasks Celery e regras internas, reduzindo divergencia entre payload HTTP, persistencia e fila.

### Integracao com o market_scraper
- O `market_alert` nao expoe um endpoint publico para parsing; a integracao acontece internamente via [`scraper/scraper_client.py`](scraper/scraper_client.py).
- O cliente envia `POST /scraper/parse` para o `market_scraper`, serializando `ParserRequest` com `url`, `product_type`, `user_id` e `metadata` opcional.
- Headers condicionais `If-None-Match` e `If-Modified-Since` sao suportados para aproveitar `304 Not Modified` e reduzir coleta desnecessaria.
- O cliente aplica rate limit por host, circuit breaker, retries com backoff e suporte a `Retry-After` antes de devolver `ParserResponse` normalizado para a camada de coleta.
- Respostas `422`, `400` e `403` com `error_code` sao preservadas como sinal operacional para bloquear URLs invalidas, respeitar robots ou tratar payloads incorretos.

---

## Workers e Tasks

### Workers Celery
- [`infraestructure/celery/celery_app.py`](infraestructure/celery/celery_app.py) cria a instancia `celery_app` usando `settings.redis_url` como broker e backend.
- A configuracao operacional fixa serializacao JSON, timezone `America/Sao_Paulo`, `worker_prefetch_multiplier`, `worker_concurrency` e prioridade maxima por fila.
- O catalogo de filas e rotas vive em [`infraestructure/celery/config.py`](infraestructure/celery/config.py), com separacao explicita entre `scraping`, `monitor`, `compare`, `notifications` e `dead_letter`.
- O bootstrap do worker repete a validacao de infraestrutura, registra signals de lifecycle e carrega os modulos de tasks explicitamente para evitar workers "saudaveis" sem tasks registradas.
- O signal `worker_ready` delega para `continuous_collector_manager`, iniciando o coletor continuo e o loop de revalidacao assim que o processo fica pronto.
- O agendamento periodico registrado nesta fase e `cleanup-cache-daily`, executado pelo Celery Beat diariamente as `03:00`.

### Filas e Topologia Celery
- [`infraestructure/celery/config.py`](infraestructure/celery/config.py) define cinco filas logicas: `scraping`, `monitor`, `compare`, `notifications` e `dead_letter`.
- Cada fila usa sua propria `Exchange` direta (`scraping`, `monitor`, `compare`, `notifications`, `dead_letter`) para manter separacao operacional entre coleta, monitoramento continuo, comparacoes, entregas e falhas permanentes.
- [`infraestructure/celery/celery_app.py`](infraestructure/celery/celery_app.py) instancia o worker com broker/backend Redis, serializacao JSON, `task_queue_max_priority=10` e timezone `America/Sao_Paulo`.
- No `docker-compose.yml`, o modulo sobe workers dedicados por papel: `celery-worker-scraping`, `celery-worker-monitor`, `celery-worker-compare` e `celery-worker-notifications`.
- O worker de scraping escuta `celery,scraping`; isso permite processar tasks sem roteamento explicito que caiam na fila padrao `celery`.
- O `worker_ready` chama [`infraestructure/worker_lifecycle.py`](infraestructure/worker_lifecycle.py), que delega para o coletor continuo iniciar o autostart e o loop de revalidacao.

### Mapa de Tasks por Fila
| Fila | Task principal | Papel no fluxo |
|------|----------------|----------------|
| `scraping` | `collect_product_task` | Coleta um monitorado ou concorrente, aplica lock Redis e persiste o resultado do scraping. |
| `monitor` | `run_continuous_collector` | Mantem o loop continuo de consumo da fila de prioridade de monitorados. |
| `monitor` | `finalize_processing_requeue` / `finalize_processing_requeue_error` | Callbacks de sucesso/erro que retornam o monitorado para a fila pronta com novo agendamento. |
| `compare` | `compare_prices_task` | Persiste comparacoes e, quando ha mudanca material, dispara avaliacao de notificacoes. |
| `notifications` | `enqueue_notifications_task` | Busca notificacoes pendentes e despacha cada uma para envio individual. |
| `notifications` | `send_notification_task` | Envia uma notificacao por canal, registra tentativa e aplica retry/dead-letter. |
| `notifications` | `send_email_verification` / `send_phone_otp` | Entregam mensagens de verificacao de cadastro (email e OTP). |
| `dead_letter` | `handle_dead_letter` | Persiste falhas permanentes de tasks em `task_failures` para auditoria. |
| `celery` ou fila informada manualmente | `reconcile_priority_queue` | Task operacional de reconciliacao da fila Redis com os monitorados ativos. |
| `monitor` via Beat | `cleanup_cache` | Limpa chaves de cache Redis com TTL invalido usando `SCAN` + `UNLINK` em lotes. |

---

## Fluxo de Trabalho 

### Fluxo Assincrono de Coleta Continua
1. O monitorado entra na fila Redis de prioridade via [`collectors/domain/collection_queue.py`](collectors/domain/collection_queue.py), normalmente a partir do lifecycle de produtos.
2. [`collectors/services/continuous_collector_manager.py`](collectors/services/continuous_collector_manager.py) executa `run_collection_loop`, garantindo singleton com lock Redis de coletor continuo.
3. O loop retira o proximo item pronto, move o ID para o conjunto `processing`, revalida estado do monitorado e despacha o grupo de coleta.
4. [`collectors/utils/continuous_dispatch.py`](collectors/utils/continuous_dispatch.py) envia a coleta do monitorado e de seus concorrentes usando [`infraestructure/celery/enqueuer.py`](infraestructure/celery/enqueuer.py).
5. A coleta do monitorado e enviada com `link` e `link_error` para os callbacks `finalize_processing_requeue` e `finalize_processing_requeue_error`, ambos executados na fila `monitor`.
6. O callback decide o novo `next_check_at`, aplica backoff quando necessario e devolve o monitorado para a fila pronta, ou o remove em cenarios bloqueantes (`paused`, `failed`, `invalid_url_blocked`).

### Fluxo Assincrono de Comparacao e Notificacao
1. [`collectors/tasks/collector_product_task.py`](collectors/tasks/collector_product_task.py) agenda comparacao apos commit quando ha mudanca material (ou quando o fluxo exige `force_compare`).
2. [`comparisons/utils/price_comparator.py`](comparisons/utils/price_comparator.py) aplica debounce Redis por monitorado antes de chamar [`infraestructure/celery/domain_task_enqueuer.py`](infraestructure/celery/domain_task_enqueuer.py).
3. `compare_prices_task` executa `run_price_comparison`, persiste `PriceComparison` e `PriceComparisonSummary` e avalia se deve gerar notificacoes.
4. Quando ha candidatos, [`notifications/services/services_notifications.py`](notifications/services/services_notifications.py) cria `event_log`, persiste notificacoes com deduplicacao/cooldown e chama `enqueue_pending_notifications`.
5. `enqueue_pending_notifications` despacha `send_notification_task` para cada item pendente na fila `notifications`.
6. `send_notification_task` chama `process_notification`, que seleciona o adapter do canal, registra tentativas, marca envio, reagenda retry ou envia para dead-letter quando o limite e atingido.

### Agendamentos e Scheduling
- O catalogo atual de Beat em [`infraestructure/celery/config.py`](infraestructure/celery/config.py) possui uma entrada explicita: `cleanup-cache-daily`, executada diariamente as `03:00` na fila `monitor`.
- [`infraestructure/tasks/maintenance_tasks.py`](infraestructure/tasks/maintenance_tasks.py) implementa essa limpeza de forma incremental, com limites de tempo, volume e tamanho de lote para nao monopolizar o Redis.
- [`collectors/tasks/priority_queue_tasks.py`](collectors/tasks/priority_queue_tasks.py) disponibiliza `reconcile_priority_queue` para recarregar a fila de prioridade, mas essa task nao esta no `BEAT_SCHEDULE` atual; hoje ela serve como rotina manual/emergencial.
- Na configuracao atual do repositorio, o `docker-compose.yml` nao declara um servico dedicado de `celery beat`, embora o codigo esteja pronto para receber esse scheduler.
- O endpoint `/health/` consulta `beat:last_success`, mas nao ha um produtor desse heartbeat dentro dos modulos carregados atualmente; se o scheduler for operado externamente, ele precisa atualizar essa chave para que o health reflita o estado real do Beat.

### Retry, Rate Limit e Resiliencia
- [`infraestructure/celery/retry_policies.py`](infraestructure/celery/retry_policies.py) centraliza os limites de retry por dominio: coleta, comparacao, enfileiramento de notificacoes, verificacoes e envio de notificacoes.
- `collect_product_task` usa `COLLECTION_RETRY` para lock contention e, adicionalmente, gerencia retries de scraping por politica propria (`RetryPolicy`) com backoff, `Retry-After`, cooldown e contadores Redis.
- [`infraestructure/resilience/rate_limiter.py`](infraestructure/resilience/rate_limiter.py) oferece dois niveis de controle: `token bucket` por host para o `ScraperClient` e `leaky bucket` para limitar onboarding de monitorados/concorrentes.
- O mesmo modulo controla contadores Redis para URLs invalidas, falhas temporarias e cooldown de scraping, evitando loops agressivos sobre alvos problematicos.
- [`infraestructure/resilience/circuit_breaker.py`](infraestructure/resilience/circuit_breaker.py) abre circuito por host quando falhas consecutivas ultrapassam o limiar configurado, reduzindo pressao sobre integracoes externas instaveis.
- O coletor continuo tambem reexecuta itens presos usando `reclaim_stale_processing`, recuperando IDs que ficaram no conjunto `processing` apos queda de worker ou perda de callback.

### Dead Letter e Auditoria
- Tasks que herdam [`infraestructure/celery/dlq_base_task.py`](infraestructure/celery/dlq_base_task.py) enviam falhas permanentes para a fila `dead_letter` quando os retries se esgotam.
- Hoje isso cobre principalmente `collect_product_task` e `send_notification_task`, que sao as rotinas com retry e risco operacional mais alto.
- [`infraestructure/celery/dlq_handler.py`](infraestructure/celery/dlq_handler.py) consome a DLQ, sanitiza mensagens de excecao e persiste o registro em `task_failures`.
- Esse fluxo evita perder contexto de falhas definitivas e cria uma trilha auditavel para diagnostico pos-incidente.

---

## Fluxos de Negocio End-to-End

### 1. Fluxo de Autenticacao (login, refresh e logout)
1. O cliente envia `POST /auth/login` com `OAuth2PasswordRequestForm`.
2. `login_user()` aplica bloqueio por IP (`block_ip`), valida credenciais e recusa contas inativas/suspensas.
3. Em sucesso, a API atualiza `last_login`, gera `access_token` (JWT) e cria `refresh_token` persistido.
4. A rota grava o refresh token em cookie HttpOnly (`set_refresh_cookie`) e retorna o par de tokens.
5. Quando o access expira, `POST /auth/refresh` resolve o refresh por cookie ou payload, revoga o token antigo e rotaciona para um novo par.
6. No encerramento de sessao, `POST /auth/logout` revoga o refresh corrente e limpa o cookie (`clear_refresh_cookie`).

### 2. Fluxo de Criacao de Produto Monitorado
1. Usuario autenticado chama `POST /monitored/scrape` com `MonitoredProductCreateScraping`.
2. O service valida e normaliza URL, verifica duplicidade por usuario e aplica rate limit de scraping.
3. O monitorado e criado em estado pendente (`create_pending_monitored_product`) e recebe `next_check_at` inicial calculado por estabilidade.
4. A API dispara coleta imediata (`enqueue_collect`) e registra o item na fila continua de prioridade (`CollectionQueue.enqueue_now`).
5. Se `initial_competitor` vier no payload, o fluxo tenta criar concorrente inicial em seguida; falha de concorrente nao desfaz o monitorado.
6. A resposta HTTP retorna `202 Accepted` com `id`, `url`, `created_at` e `next_check_at`.

### 3. Fluxo de Coleta de Precos (API -> Celery -> scraper -> persistencia)
1. O item pode chegar a coleta por onboarding imediato ou pelo loop continuo (`run_continuous_collector`).
2. `collect_product_task` valida payload, resolve alvo (`monitored` ou `competitor`) e aplica lock Redis por produto.
3. O service de scraping chama `ScraperClient.fetch()` para `POST /scraper/parse`, reaproveitando `ETag` e `Last-Modified` quando disponiveis.
4. Em `200`, os dados normalizados sao persistidos (preco, disponibilidade, metadados e timestamps); em `304`, apenas `last_checked` e agenda sao atualizados.
5. O resultado gera `outcome` (`success`, `not_modified`, `no_result`, `error`) e pode acionar retries com backoff/cooldown para falhas temporarias.
6. Os callbacks `finalize_processing_requeue` e `finalize_processing_requeue_error` devolvem o monitorado para a fila de prioridade com novo agendamento.

### 4. Fluxo de Comparacao de Precos
1. A comparacao e agendada apos coleta material (`schedule_comparison_after_commit`) ou por recomputacao explicitamente solicitada.
2. `compare_prices_task` chama `run_price_comparison()` para o `monitored_id`.
3. O service carrega monitorado + concorrentes e, se o monitorado estiver pausado/inativo, persiste um resumo stub com motivo (`ignored_due_to_inactive`).
4. Em monitorado ativo, `compare_prices()` calcula discrepancias, menor/maior concorrente, media e ranking.
5. O resultado e persistido em `PriceComparison` e agregado em `PriceComparisonSummary`.
6. A task so continua para notificacao quando ha contexto valido (usuario encontrado e mudanca relevante).

### 5. Fluxo de Notificacao
1. `evaluate_and_create_notifications()` recebe snapshots anterior/atual e busca preferencias + regras do usuario.
2. O evaluator detecta eventos (`price_change`, `availability_change`, etc.), resolve canais elegiveis e renderiza mensagens por template.
3. Para cada candidato, o service aplica deduplicacao e cooldown em Redis + banco, adquire lock e persiste `event_log` e `notification`.
4. `enqueue_pending_notifications()` despacha IDs pendentes para `send_notification_task` na fila `notifications`.
5. `process_notification()` seleciona adapter de canal, registra tentativa e marca `sent` ou `failed`.
6. Em sucesso, registra cooldown; em falha, reagenda por backoff ate `max_attempts`; ao esgotar, marca dead-letter.

### 6. Fluxo de Usuario Consultando Alertas e Estado
1. O frontend autenticado consulta `GET /notifications/` para listar alertas persistidos com paginacao.
2. Para contextualizar impacto comercial, consulta `GET /comparisons/{monitored_id}/summary` e/ou historico em `/comparisons/{monitored_id}`.
3. Ajustes de preferencia sao feitos por `GET/POST /notifications/preferences` e `GET/PATCH /settings/notifications`.
4. O painel de estado operacional combina `GET /monitored`, `GET /competitors` e `GET /dashboard/stats`.
5. Com isso, o usuario fecha o ciclo completo: monitora produtos, recebe alertas, revisa comparacoes e ajusta canais de entrega.

---

## Configuração
As configuracoes combinam a base compartilhada em `shared/core/config_base.py` com overrides especificos de [`core/config_alert.py`](core/config_alert.py).

### Ordem de carregamento de ambiente
1. `.env.common` fornece parametros compartilhados da suite.
2. O arquivo indicado por `ENV_FILE` sobrescreve os defaults compartilhados.
3. No `docker-compose.yml`, o `market_alert` monta `./backend/market_alert/.env.market_alert` e define `ENV_FILE=.env.market_alert`, de modo que o modulo resolve seu arquivo local de servico dentro do container.
4. Variaveis de ambiente exportadas diretamente continuam tendo precedencia no processo.

### Categorias de variaveis
| Categoria | Variaveis relevantes |
|-----------|----------------------|
| Infra base | `DATABASE_URL`, `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD`, `LOG_LEVEL`, `LOG_FORMAT` |
| API e frontend | `FRONTEND_ORIGINS` |
| Autenticacao | `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `REFRESH_TOKEN_COOKIE_*` |
| Protecao operacional | `BRUTE_FORCE_MAX_ATTEMPTS`, `BRUTE_FORCE_BLOCK_DURATION`, `REGISTRATION_MAX_PER_HOUR` |
| Coleta continua | `PRODUCT_LOCK_TTL_SECONDS`, `PRODUCT_LOCK_TTL_MIN_SAFE_SECONDS`, `COLLECT_INTERVAL_*`, `STABILITY_DAYS_*`, `CONTINUOUS_WORKER_*`, `CONTINUOUS_COLLECTOR_LOCK_TTL_SECONDS`, `PRIORITY_QUEUE_*` |
| Integracao com scraper | `SCRAPER_SERVICE_URL`, `SCRAPER_*TIMEOUT*`, `SCRAPER_RETRY_*`, `SCRAPER_HOST_*`, `SCRAPER_CIRCUIT_*`, `SCRAPER_FORCE_REFRESH_TTL_SECONDS`, `SCRAPER_NO_RESULT_RETRY_SECONDS`, `MAX_COMPETITORS_PER_MONITORED` |
| Comparacao | `PRICE_TOLERANCE`, `PRICE_CHANGE_THRESHOLD`, `COMPARE_RATE_LIMIT`, `COMPETITIVENESS_THRESHOLD_*`, `COMPARISON_IDEMPOTENCY_TTL_SECONDS`, `COMPARISON_STORE_RAW_RESULT` |
| Notificacoes | `SMTP_*`, `TWILIO_*`, `FCM_SERVER_KEY`, `DEFAULT_COOLDOWN_SECONDS`, `MIN_PRICE_DELTA_PERCENT`, `NOTIFICATION_*` |
| Verificacao de cadastro | `EMAIL_VERIFICATION_EXPIRE_MINUTES`, `PHONE_VERIFICATION_*`, `VERIFICATION_RESEND_*` |
| Circuit breaker compartilhado | `CIRCUIT_*` |

Falhas de configuracao consideradas obrigatorias interrompem o processo cedo: `DATABASE_URL` e `SECRET_KEY` sao validados na criacao de `settings`.

Exemplo mínimo de `.env.market_alert`:
```env
SCRAPER_HOST_RATE_LIMIT=20
SCRAPER_HOST_RATE_WINDOW_SECONDS=60
SCRAPER_HOST_RETRY_MAX_ATTEMPTS=4
SCRAPER_HOST_RETRY_WINDOW_SECONDS=60
SCRAPER_RATE_LIMIT_COOLDOWN_SECONDS=600
SCRAPER_INVALID_URL_MAX_ATTEMPTS=3
SCRAPER_INVALID_URL_TTL_SECONDS=86400

REFRESH_TOKEN_COOKIE_NAME=refresh_token
REFRESH_TOKEN_COOKIE_PATH=/
REFRESH_TOKEN_COOKIE_SECURE=0
REFRESH_TOKEN_COOKIE_SAMESITE=lax
FRONTEND_ORIGINS='["http://localhost:5173"]'

COLLECT_INTERVAL_UNSTABLE_MIN=300
COLLECT_INTERVAL_UNSTABLE_MAX=600
COLLECT_INTERVAL_STABLE_MIN=600
COLLECT_INTERVAL_STABLE_MAX=1200
COLLECT_INTERVAL_VERY_STABLE_MIN=1200
COLLECT_INTERVAL_VERY_STABLE_MAX=1800

STABILITY_DAYS_UNSTABLE=1
STABILITY_DAYS_STABLE=3
STABILITY_DAYS_VERY_STABLE=7

COLLECT_PRODUCT_TIMEOUT=60
COMPARE_PRICES_TIMEOUT=30
CONTINUOUS_LOOP_SLEEP_MIN=5
CONTINUOUS_LOOP_SLEEP_MAX=15

CONTINUOUS_WORKER_POLL_INTERVAL=1.0
CONTINUOUS_WORKER_BATCH_SIZE=20
CONTINUOUS_WORKER_IDLE_SLEEP=2.0
CONTINUOUS_WORKER_PROCESSING_TTL_SECONDS=900
CONTINUOUS_WORKER_STOP_REDIS_KEY=market_alert:continuous_worker:stop
CONTINUOUS_WORKER_STOP_FILE=/tmp/market_alert_continuous_worker.stop

CONTINUOUS_COLLECTOR_AUTOSTART=1
CONTINUOUS_COLLECTOR_AUTOSTART_TTL=60

PRIORITY_QUEUE_KEY=market_alert:priority_queue
PRIORITY_QUEUE_PROCESSING_KEY=market_alert:priority_queue:processing

SCRAPER_SERVICE_URL=http://market_scraper:8000
```

---

## Seguranca e Observabilidade
- **Segurança:**
  - Autenticacao: JWT bearer para acesso a API (`core/jwt.py`) e refresh token rotativo com cookie HttpOnly (`auth/utils/cookies_auth.py`).
  - Autorizacao (RBAC): rotas administrativas exigem role `admin` e ownership e validado nos services de acesso (`services_access_control.py`, `auth_context.py`).
  - Validacao de entrada: contratos Pydantic em `schemas/`, validacao de URLs com normalizacao canonica e validacao de contatos (email/telefone) antes de persistir ou notificar.
  - Rate limiting: `slowapi` por IP na API, protecao anti-bruteforce em Redis no login e limitadores `leaky bucket`/`token bucket` para scraping e onboarding.

- **Observabilidade:**
  - Auditoria e rastreabilidade: logs estruturados com `trace_id`, registro de falhas permanentes em `task_failures` via DLQ e volume dedicado `audit-logs` no compose.
  - Health checks: `/health/` e `/health/readiness` monitoram disponibilidade de PostgreSQL/Redis e estado operacional do scheduler.
  - Observabilidade de workers: logging dedicado em `logging_config.py`, supressao de ruido em bibliotecas de infraestrutura e alertas para configuracoes de lock inseguras.

---

> Nota Final: o README do `market_alert` deve sempre estar atualizado e coerente com o estado atual do sistema, orquestração, tratamendo dos dados e regras de negócio, para evitar informações falsas e desatualizadas.
