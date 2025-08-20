Este arquivo documenta os principais **agentes de software e serviços automatizados** utilizados no projeto **MarketAlert**. Ele serve como referência para desenvolvedores e ferramentas (como o Codex) entenderem como o sistema é estruturado, especialmente os serviços que rodam em segundo plano ou executam tarefas programadas.

## Diretrizes para agentes de IA e contribuidores

- Ao modificar o código, adicione **comentários e docstrings em Português**.
- Após qualquer alteração execute os testes com `pytest` para garantir a integridade do projeto.
- Prefira utilizar `rg` para buscas no código em vez de `grep -R`.
- Os commits devem ser feitos no branch atual, sem criação de novas branches.

## Estrutura do repositório

- `market_alert/` – API principal e tarefas Celery.
- `market_scraper/` – serviço de scraping dedicado.
- `shared/` – utilidades e componentes compartilhados entre os serviços.

---

## 1. API Principal (`api`)

- **Tipo:** FastAPI application
- **Responsabilidade:** Servir endpoints REST para cadastro, scraping e monitoramento de produtos.
- **Inicialização:** Via `uvicorn main:app`
- **Resultado:** Interface principal de interação com usuários e serviços automatizados.

---

## 2. Celery Worker (`celery-worker`)

- **Tipo:** Worker de background com Celery
- **Responsabilidade:** Executar tarefas assíncronas como scraping, comparação de preços, envio de alertas e coleta de métricas.
- **Inicialização:** `celery -A market_alert.core.celery_app:celery_app worker --loglevel=info`
- **Tarefas Executadas:**
- `collect_product_task`
- `collect_competitor_task`
- `compare_prices_task`
- `send_notification_task`
- `dispatch_price_alert_task`
- `send_alert_task`

---

## 3. Celery Beat (`celery_beat`)

- **Tipo:** Agendador de tarefas periódicas
- **Responsabilidade:** Executar tarefas recorrentes com base em agendamento (`beat_schedule`)
- **Inicialização:** `python beat_with_metrics.py`
- **Tarefas Programadas:** 
- Coleta de métricas (`collect_celery_metrics`)
- limpeza de cache (`cleanup_cache`)
- Rechecagem de scraping (`recheck_monitored_products`, `recheck_competitor_products`)

---

## 4. Scraping Agents

### a. `collect_product_task`

- **Tipo:** Celery Task
- **Responsabilidade:** Scraping de produto monitorado
- **Input:** URL, user_id, preço_alvo, identificação
- **Resultado:** Dados do produto atualizados no banco de dados

### b. `collect_competitor_task`

- **Tipo:** Celery Task
- **Responsabilidade:** Scraping de produto concorrente
- **Input:** URL, monitored_product_id
- **Resultado:** Compara preço com produto monitorado e dispara alerta se necessário

---

## 5. Price Comparison Agent (`compare_prices_task`)

- **Tipo:** Celery Task
- **Responsabilidade:** Comparar preços entre produtos monitorados e concorrentes
- **Resultado:** Geração de alertas se houver preço mais baixo

---

## 6. Alert Agents

- **Tipo:** Celery Task
- **Responsabilidade:** Enviar notificações de preço para um produto monitorado em todos os canais configurados
- **Input:** ID do produto monitorado + lista de alertas
- **Resultado:** Disparo de alertas correspondentes

### b. `dispatch_price_alert_task`

- **Tipo:** Celery Task
- **Responsabilidade:** Enviar um único alerta de preço específico
- **Input:** ID do produto monitorado + alerta individual
- **Resultado:** Notificação singular para o usuário

### c. `send_alert_task`

- **Tipo:** Celery Task
- **Responsabilidade:** Realizar o envio efetivo via email, SMS, push, WhatsApp ou Slack
- **Input:** ID do registro `NotificationLog`
- **Resultado:** Mensagem enviada ao canal designado

---

## 7. Utilitários e Gerenciadores Internos

| Nome                          | Função                                                    |
|-------------------------------|-----------------------------------------------------------|
| `IntelligentUserAgentManager` | Rotação de User-Agent                                     |
| `CookieManager`               | Gerência de cookies por sessão                            |
| `ThrottleManager`             | Controle de requisições com token bucket e jitter         |
| `RateLimiter`                 | Limite de taxa baseado em janela deslizante (Redis + Lua) |
| `CircuitBreaker`              | Evita falhas em cascata após bloqueios 403/429            |
| `BlockRecoveryManager`        | Detecção e resposta a CAPTCHA e bloqueios HTTP            |
| `HumanizeDelayManager`        | Simula delays humanos nas requisições                     |
| `AdaptiveRecheckManager`      | Define quando reexecutar o scraping                       | 
| `IntelligentCacheManager`     | Cache adaptativo por produto                              |
| `NotificationManager`         | Integração com canais de notificação                      |

---

## 8. Métricas e Observabilidade

### a. Prometheus

- **Tipo:** Coletor de métricas
- **Responsabilidade:** Monitorar APi, Celery, audit logs e sistema
- **Rota `/metrics`** exposta via FastAPI e Celery Beat

### b. Alertmanager

- **Tipo:** Serviço de alerta
- **Responsabilidade:** Envia notificações para canais (como Slack)

### c. Loki + Promtail

- **Tipo:** Centralizador de logs
- **Responsabilidade:** Captura e envia logs de serviços para o Grafana

### d. Node Exporter e cAdvisor

- **Tipo:** Exportadores de métricas
- **Responsabilidade:** Coletar estatísticas do host e containers

---

## 9. Teste de Carga (`locust`)

- **Tipo:** Ferramenta de teste de performance
- **Responsabilidade:** Simular carga real no sistema com múltiplos usuários
- **Arquivo:** ``tests/load/locustfile.py``

---

## 10. Audit Exporter (`/audit`)

- **Tipo:** Aplicação FastAPI secundária
- **Responsabilidade:** Exportar arquivos JSON de auditoria em métricas Prometheus
- **Rota:** ``/audit/metrica``

---

## 11. Redis Init Helper (`redis-init`)

- **Tipo:** Serviço auxiliar
- **Responsabilidade:** Carregar scripts Lua no Redis para RateLimiter
- **Comando Executado:** 
```sh
redis-cli SCRIPT LOAD "$(cat infra/redis-scripts/sliding_window.lua)"
```
Este helper garante que o script esteja disponível no Redis.
