# Inventário do backend `market_alert`

Este documento consolida as rotas públicas, contratos Pydantic, operações CRUD e tarefas Celery ativas para guiar a limpeza do backend e garantir compatibilidade com o frontend.

## Rotas expostas e contratos

| Router/base | Método e caminho | Request schema | Response schema | Uso esperado no frontend |
| --- | --- | --- | --- | --- |
| `/auth` | POST `/` | `OAuth2PasswordRequestForm` | `TokenPairResponse` | Login e obtenção de tokens de sessão. |
| `/auth` | POST `/refresh` | `RefreshRequest` | `TokenPairResponse` | Renovação de tokens para sessões ativas. |
| `/auth` | POST `/logout` | `TokenRevokeRequest` | `204 No Content` | Encerrar sessão e invalidar refresh. |
| `/auth/profile` | POST `/change-password` | `ChangePasswordRequest` | `{msg}` simples | Ajuste de senha pelo painel autenticado. |
| `/auth/profile` | POST `/change-email` | `ChangeEmailRequest` | `{msg}` simples | Alteração de e-mail com revalidação. |
| `/auth/reset_password` | POST `/request` | `ResetPasswordRequest` | `{msg}` simples | Disparo do fluxo de recuperação de senha. |
| `/auth/reset_password` | POST `/confirm` | `ResetPasswordConfirmRequest` | `{msg}` simples | Confirmação de token e definição de nova senha. |
| `/auth/verify` | POST `/request` | `None` (usa usuário autenticado) | `{msg}` simples | Solicita token de verificação de e-mail. |
| `/auth/verify` | POST `/confirm` | `EmailTokenRequest` | `{msg}` simples | Confirmação de e-mail para liberar recursos. |
| `/users` | POST `/` | `UserCreate` | `UserResponse` | Cadastro inicial a partir do frontend. |
| `/users` | PUT `/{user_id}` | `UserUpdate` | `UserResponse` | Ajustes administrativos de perfil. |
| `/users` | PUT `/{user_id}/status` | `{active: bool}` | `UserResponse` | (Interno) habilitar/desabilitar usuário. |
| `/users` | GET `/me` | - | `UserResponse` | Carregar dados do usuário logado. |
| `/monitored` | POST `/scrape` | `MonitoredProductCreateScraping` | `MonitoredScrapeCreationResponse` | Agendar criação de produto monitorado. |
| `/monitored` | GET `/` | query `page`, `per_page`, `query`, `status` | `PaginatedMonitoredProductsResponse` | Listagem principal do painel. |
| `/monitored` | GET `/featured` | filtros internos | `List[MonitoredProductResponse]` | Destaques para dashboard/home. |
| `/monitored` | GET `/{product_id}` | path `product_id` | `MonitoredProductResponse` | Detalhe de item monitorado. |
| `/monitored` | DELETE `/{product_id}` | path `product_id` | `MonitoredProductResponse` | Remoção lógica do monitoramento. |
| `/competitors` | POST `/scrape` | `CompetitorProductCreateScraping` | `CompetitorScrapeCreationResponse` | Cadastrar concorrente e agendar scraping. |
| `/competitors` | GET `/` | query `monitored_id`, `page`, `per_page`, `order_by`, `include_paused` | `PaginatedCompetitorResponse` | Listar concorrentes de um monitorado. |
| `/competitors` | POST `/bulk/resume` | `BulkCompetitorActionRequest` | `BulkCompetitorActionResult` | Reativar concorrentes em massa. |
| `/competitors` | POST `/bulk/pause` | `BulkCompetitorActionRequest` | `BulkCompetitorActionResult` | Pausar concorrentes em massa. |
| `/competitors` | POST `/bulk/remove` | `BulkCompetitorActionRequest` | `BulkCompetitorActionResult` | Remover concorrentes selecionados. |
| `/competitors` | DELETE `/{monitored_product_id}` | path `monitored_product_id` | `List[CompetitorProductResponse]` | Limpar concorrentes de um monitorado. |
| `/comparisons` | GET `/{monitored_id}` | query `page`, `per_page` | `PaginatedPriceComparisonResponse` | Histórico paginado de comparações. |
| `/comparisons` | GET `/{monitored_id}/summary` | - | `PriceComparisonSummaryResponse` | Resumo consolidado exibido no produto. |
| `/comparisons` | GET `/detail/{comparison_id}` | path `comparison_id` | `PriceComparisonResponse` | Detalhe granular da comparação selecionada. |
| `/comparisons` | POST `/{monitored_id}/run` | `PriceComparisonRunRequest` (opcional) | `{result, alerts}` | Forçar nova comparação manual. |
| `/alerts` | POST `/` | `AlertRuleCreate` | `AlertRuleResponse` | Criar regra de alerta por preço/variação. |
| `/alerts` | GET `/` | query `monitored_product_id?` | `List[AlertRuleResponse]` | Listar regras do usuário/monitorado. |
| `/alerts` | GET/PUT/PATCH/DELETE `/{rule_id}` | `AlertRuleUpdate` ou toggle | `AlertRuleResponse` | Manter regras existentes. |
| `/notifications` | GET `/ws` | - | JSON com mensagem | Indica desativação temporária do websocket. |
| `/notifications` | GET `/logs` | query `limit`, `offset`, `start`, `end`, `channel`, `success`, `alert_rule_id`, `cursor` | `List[NotificationLogResponse]` | Histórico de envios para painel e auditoria. |
| `/dashboard` | GET `/stats` | - | `dict[str,int]` | Cards agregados de monitorados/concorrentes/alertas. |
| `/health` | GET `/` | - | JSON com status de Postgres/Redis/beat | Probes de disponibilidade para infraestrutura. |

## Schemas compartilhados relevantes

- `schemas_products.py`: respostas de produtos monitorados e concorrentes (`MonitoredProductResponse`, `PaginatedMonitoredProductsResponse`, `CompetitorProductResponse`, etc.).
- `schemas_comparisons.py`: estruturas de comparações e resumo (`PaginatedPriceComparisonResponse`, `PriceComparisonSummaryResponse`, `PriceComparisonRunRequest`).
- `schemas_alert_rules.py`: criação/edição de regras e histórico de notificações (`AlertRuleCreate`, `AlertRuleResponse`, `NotificationLogResponse`).
- `schemas_auth.py`: contratos de autenticação e perfil (`TokenPairResponse`, `RefreshRequest`, `ChangePasswordRequest`, `ResetPassword*`, `EmailTokenRequest`).
- `backend/shared/schemas/shared_schemas_products.py`: contratos de criação para scraping (`MonitoredProductCreateScraping`, `CompetitorProductCreateScraping`) compatíveis com `market_scraper`.

## Operações CRUD e consumidores

- `crud_monitored.py`: criação/atualização de monitorados e paginação; usado por `routes_monitored` e consultas auxiliares de `routes_comparisons`.
- `crud_competitor.py`: criação/paginação/ações em massa de concorrentes; chamado por `routes_competitors` e auxilia `run_price_comparison`.
- `crud_comparison.py`: persistência e leitura de comparações/resumos; utilizado pelas rotas de comparações e pelo serviço de comparação.
- `crud_alert_rules.py`: criação, leitura, atualização e remoção de regras de alerta; consumido por `routes_alerts` e tasks de notificação.
- `crud_user.py` e `crud_refresh_token.py`: criação/atualização de usuários, gestão de tokens; consumidos por rotas de autenticação e administração.
- `crud_notification_logs.py`: registro e listagem de logs de notificações; usado por `routes_notifications` e tasks de alerta.
- `crud_errors.py`: persistência e consulta de erros de scraping; usado por `routes_monitoring_errors` para diagnósticos.

## Tarefas Celery e agendamentos

- `tasks.scraper_tasks`: coleta de produtos monitorados e concorrentes (`collect_product_task`, `collect_competitor_task`) acionadas pelas rotas `/monitored/scrape` e `/competitors/scrape`.
- `tasks.monitor_tasks`: rotinas periódicas para reprocessar monitorados e concorrentes, chamadas via Celery Beat.
- `tasks.compare_prices_tasks`: cálculo e armazenamento de comparações automáticas (usado pelo motor de comparação e dashboards).
- `tasks.alert_tasks`: envio de alertas e notificações, incluindo reintentos e limites (`send_alert_task`, `send_notification_task`, `dispatch_price_alert_task`).
- `tasks.metrics_tasks`: coleta de métricas do worker para Prometheus/beat.
- `core.celery_app`: configura filas `scraping` e `monitor`, roteamento dedicado e agendamentos do Beat para métricas; `beat_with_metrics.py` expõe monitoramento do scheduler.

## Observações para consolidação

- Priorizar apenas os endpoints acima como superfície pública, mantendo contratos Pydantic alinhados ao frontend e à documentação `products_api_contract.md`.
- Rotas internas (ex.: `/users/{id}/status`, `/notifications/ws`) podem ser mantidas, mas sinalizadas como administrativas/temporárias.
- Garantir que responses serializem preços/decimais em string conforme contratos já adotados e que erros mantenham mensagens em português para o frontend