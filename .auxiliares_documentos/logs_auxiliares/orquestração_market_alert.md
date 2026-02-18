# Orquestração e Arquitetura do Market Alert

### 1. Conceito Central

O `market_alert` implementa uma **arquitetura de orquestração distribuída baseada em Celery com workers dedicados**, onde diferentes tipos de tarefas são processadas por workers especializados que consomem filas isoladas. A coordenação central acontece através de um **loop contínuo (continuous collector)** que consome uma **fila de prioridade baseada em Redis Sorted Sets**, despachando coletas assíncronas para workers de scraping enquanto mantém controle de estado através de locks distribuídos.

---

### 2. Análise Guiada do Código

#### 2.1 Arquitetura de Workers: Separação de Responsabilidades

**O Que Faz:**  
O sistema define **4 workers Celery independentes**, cada um com sua própria fila e nível de concorrência:

```yaml
celery-worker-scraping:    # Fila: scraping    | Concorrência: 4
celery-worker-monitor:     # Fila: monitor     | Concorrência: 1
celery-worker-compare:     # Fila: compare     | Concorrência: 2
celery-worker-notifications: # Fila: notifications | Concorrência: 2
```

**Por Que é Feito Assim (Decisão Técnica):**  
A separação em workers dedicados segue o **padrão de segregação de responsabilidades** para evitar que:
- Tarefas lentas de scraping bloqueiem comparações rápidas
- O loop contínuo (monitor) seja interrompido por outras operações
- Notificações disputem recursos com coletas de dados

A **concorrência 1 no monitor** é crítica: garante que apenas uma instância do loop contínuo execute por vez, evitando duplicação de tarefas e race conditions na fila de prioridade.

**Como se Encaixa no Todo:**  
Os workers são orquestrados pelo docker-compose.yml, compartilhando o mesmo Redis (broker + result backend) e PostgreSQL, mas operando de forma independente. Quando uma tarefa é enfileirada com `.apply_async(queue="scraping")`, apenas o `celery-worker-scraping` a processa.

---

#### 2.2 Fila de Prioridade: Redis Sorted Sets como Scheduler

**O Que Faz:**  
A classe services_priority_queue.py encapsula operações sobre dois sorted sets no Redis:
- `PRIORITY_QUEUE_KEY`: fila principal ordenada por timestamp (`next_check_at`)
- `PRIORITY_QUEUE_PROCESSING_KEY`: conjunto auxiliar de itens em processamento

Operação atômica central via script Lua:
```lua
-- POP_DUE_SCRIPT: Remove item da fila principal se o score <= now
-- e move para processamento atomicamente
```

**Por Que é Feito Assim (Decisão Técnica):**  
- **Sorted Sets** mantêm ordenação automática por score (timestamp), permitindo consultas eficientes de "próximos itens vencidos"
- **Scripts Lua** garantem atomicidade sem race conditions entre múltiplos workers tentando consumir o mesmo item
- O conjunto de **processamento separado** permite rastrear quais itens estão sendo coletados e recuperá-los (`reclaim_stale_processing`) se o worker morrer antes de concluir

**Alternativas consideradas:** 
- Celery Beat com tarefas agendadas individuais → não escala para milhares de produtos
- Banco de dados como fila → latência maior e carga desnecessária no PostgreSQL
- RabbitMQ delayed messages → adiciona dependência extra e não oferece vantagem clara sobre Redis

**Como se Encaixa no Todo:**  
A fila é alimentada quando:
1. Um novo produto é criado via routes_monitored.py
2. Uma coleta é concluída e o worker calcula o próximo `next_check_at` baseado na estabilidade do preço

---

#### 2.3 Loop Contínuo: O Orquestrador Principal

**O Que Faz:**  
A task continuous_collector_task.py **roda indefinidamente** (sem time limit) no `celery-worker-monitor`:

```python
while True:
    # 1. Adquire lock distribuído (garante única instância ativa)
    # 2. Consulta próximos itens vencidos (batch_size=20)
    # 3. Para cada item:
    #    - Carrega monitorado do banco
    #    - Ignora se pausado/failed
    #    - Despacha coleta assíncrona (monitored + competitors)
    #    - Mantém no processamento até callback concluir
    # 4. Dorme poll_interval (1.0s padrão)
```

**Por Que é Feito Assim (Decisão Técnica):**  
- **Loop ativo vs. Celery Beat**: O Beat não escala para milhares de produtos com horários individuais. O loop consome uma fila compartilhada dinamicamente.
- **Lock distribuído via Redis**: Evita múltiplas instâncias do loop rodando simultaneamente em deploys com múltiplos workers.
- **Retenção em processamento**: Quando um monitorado é despachado, ele permanece no conjunto `processing` até que a task `collect_product_task` termine e execute o callback `finalize_processing_requeue`. Isso evita reprocessamento enquanto a coleta está em andamento.
- **Reclaim de itens travados**: Se um worker morrer durante coleta, o item fica "preso" em processamento. O método `reclaim_stale_processing(TTL)` retorna itens para a fila após o TTL expirar.

**Problemas identificados nesta implementação:**
1. **`time.sleep(poll_interval)` bloqueante**: Em pool `prefork` (padrão), isso não é problema. Mas se migrar para `gevent`/`eventlet`, essa chamada bloquearia outras greenlets.
2. **Loop infinito sem time limit**: Se o worker precisar reiniciar gracefully, não há mecanismo de parada limpa além de matar o processo.
3. **Processamento sequencial**: Apesar do batch_size=20, o loop processa os 20 itens um por vez (não em paralelo), criando latência acumulada.

**Como se Encaixa no Todo:**  
Este é o **coração do sistema**. Sem ele rodando, coletas periódicas param completamente. O autostart via `CONTINUOUS_COLLECTOR_AUTOSTART=1` garante que o loop inicie quando o worker sobe.

---

#### 2.4 Task de Coleta: O Executor

**O Que Faz:**  
A task collector_product_task.py é o **único ponto de entrada para scraping**:

```python
def collect_product_task(payload):
    # 1. Valida payload (monitored ou competitor)
    # 2. Tenta adquirir lock Redis (TTL=20s padrão)
    # 3. Se lock falha: retorna ScrapeResult(status="no_result")
    # 4. Chama ScraperClient para obter dados
    # 5. Persiste no banco (PriceHistory, Monitored/Competitor)
    # 6. Calcula next_check_at baseado em estabilidade
    # 7. Libera lock
    # 8. Dispara compare_prices_task se preço mudou
```

**Por Que é Feito Assim (Decisão Técnica):**  
- **Lock Redis como única exclusão mútua**: Não há flags `is_processing` no banco. O lock evita que dois workers coletem o mesmo produto simultaneamente.
- **TTL do lock (20s)**: Se o worker morrer durante scraping, o lock expira automaticamente e outro worker pode tentar.
- **Retorno `no_result` quando lock falha**: Não é erro; apenas sinaliza concorrência. O continuous collector não reage especialmente a isso.
- **Cálculo adaptativo de estabilidade**: Produtos com preço estável são rechecados menos frequentemente (5-30 min), economizando recursos.

**Decisões questionáveis:**
1. **Lock TTL fixo de 20s**: Se um scraping legítimo demorar mais (site lento), o lock expira e outro worker tenta simultaneamente.
2. **Retries com `self.retry(countdown=...)`**: Usa `time.sleep` implícito do Celery, que pode acumular tarefas atrasadas na fila.
3. **Comparação disparada dentro da task**: Adiciona acoplamento; idealmente seria um evento separado.

**Como se Encaixa no Todo:**  
É o "trabalhador braçal" que executa o scraping real. Consumido por `celery-worker-scraping` (concorrência 4), processa até 4 produtos simultaneamente.

---

#### 2.5 Despacho e Callbacks: Ligando as Pontas

**O Que Faz:**  
O módulo continuous_dispatch.py contém a função `_collect_group` que:
1. Constrói payload do monitorado
2. Obtém lista de competitors do banco
3. Despacha task com callbacks assíncronos:
```python
on_complete=finalize_processing_requeue  # Remove do processamento e reenfileira
on_error=finalize_processing_requeue_error  # Trata falhas
```

**Por Que é Feito Assim (Decisão Técnica):**  
- **Callbacks Celery (link/link_error)**: Garantem que, independente de sucesso ou falha, o item será removido do processamento e reenfileirado.
- **Despacho assíncrono**: O loop contínuo não espera scraping terminar; apenas enfileira e continua processando o próximo item.
- **Competitors enfileirados em sequência**: Não há batching; cada competitor é despachado individualmente com delay incremental para evitar picos.

**Problema crítico identificado:**
O callback `finalize_processing_requeue` **só executa se a task retornar sucesso**. Se houver exceção não tratada ou timeout hard, o callback nunca roda e o item fica preso em processamento até o `reclaim_stale_processing` recuperá-lo (potencialmente minutos depois).

**Como se Encaixa no Todo:**  
Essa camada de orquestração conecta o loop contínuo (que decide *quando* coletar) com a task de coleta (que decide *como* coletar), gerenciando o ciclo de vida do estado no Redis.

---

### 3. Resumo do Fluxo em Execução

**Entrada:**  
Usuário cria um produto monitorado via `POST /monitored/scrape` com URL do produto.

**Processamento:**

1. **[API]** routes_monitored.py → `schedule_monitored_scrape()`
   - Valida duplicidade
   - Cria registro mínimo no banco (`status=pending`)
   - Calcula `next_check_at` inicial
   - **Enfileira na fila de prioridade Redis** via `enqueue_monitored_now()`
   - **Despacha coleta imediata** via `enqueue_monitored_collection()` → fila `scraping`
   - Retorna `202 Accepted`

2. **[Worker Monitor]** Loop contínuo em `run_continuous_collector`
   - Busca próximo item vencido na fila de prioridade
   - Move para conjunto de processamento
   - Despacha `collect_product_task` para fila `scraping`
   - Despacha tasks dos competitors vinculados

3. **[Worker Scraping]** `collect_product_task` (concorrência 4)
   - Adquire lock Redis (`product:{id}` por 20s)
   - Chama `ScraperClient.parse()` → HTTP POST ao `market_scraper`
   - Recebe `ParserResponse` com preço/disponibilidade
   - Cria/atualiza `MonitoredProduct` e insere `PriceHistory`
   - Calcula `next_check_at` baseado em estabilidade
   - Libera lock
   - Se preço mudou: enfileira `compare_prices_task` na fila `compare`
   - Executa callback `finalize_processing_requeue`

4. **[Worker Monitor]** Callback `finalize_processing_requeue`
   - Remove monitorado do conjunto de processamento
   - Reenfileira na fila de prioridade com novo `next_check_at`
   - Loop contínuo pode processá-lo novamente quando vencer

5. **[Worker Compare]** `compare_prices_task` (se disparado)
   - Carrega histórico de preços dos competitors
   - Calcula `competitiveness_status` (cheaper, competitive, expensive)
   - Atualiza tabela `price_comparison`
   - Dispara notificações se necessário

**Saída:**  
- **Banco:** Registros atualizados em `monitored_products`, `price_history`, `price_comparison`
- **Redis:** Monitorado reenfileirado para próxima rechecagem
- **Frontend:** Pode consultar dados via `GET /monitored/{id}`

---

### 4. Respondendo às Suas Perguntas

#### 4.1 Diagrama Real do Sistema Atual

**Como o scraping é disparado?**
1. **Manual (imediato):** `POST /monitored/scrape` → `enqueue_monitored_collection()` → fila `scraping`
2. **Automático (periódico):** Loop contínuo consome fila de prioridade → `_collect_group()` → fila `scraping`

**Onde o estado da coleta é controlado?**
- **Agendamento:** Redis Sorted Set (`PRIORITY_QUEUE_KEY`)
- **Processamento ativo:** Redis Sorted Set (`PRIORITY_QUEUE_PROCESSING_KEY`)
- **Lock de concorrência:** Redis key `product:{id}` com TTL
- **Dados persistidos:** PostgreSQL (`monitored_products`, `price_history`)

**Filas existentes e seus processos:**

| Fila | Worker | O Que Executa |
|------|--------|---------------|
| `scraping` | celery-worker-scraping (4) | `collect_product_task` - scraping de um produto por vez com lock Redis |
| `monitor` | celery-worker-monitor (1) | `run_continuous_collector` - loop infinito que consome fila de prioridade e despacha coletas |
| `compare` | celery-worker-compare (2) | `compare_prices_task` - calcula competitividade após mudanças de preço |
| `notifications` | celery-worker-notifications (2) | `send_notification_task`, `verification_tasks` - entrega de alertas com retry |

---

#### 4.2 Modelo de Orquestração

**Como está a orquestração atual?**
**Modelo híbrido com pontos de centralização e pontos distribuídos:**

✅ **Bem organizado:**
- Workers dedicados com responsabilidades claras
- Fila de prioridade centralizada no Redis
- Lock distribuído para evitar coletas simultâneas

❌ **Desorganizado/Espalhado:**
- **Agendamento misturado:** Coletas imediatas (onboarding) e periódicas (loop contínuo) usam caminhos diferentes
- **Estado fragmentado:** Parte no Redis (agendamento, locks), parte no banco (dados), sem *single source of truth*
- **Callbacks aninhados:** `finalize_processing_requeue` depende de `collect_product_task` retornar sucesso; falhas fora do tratamento deixam itens órfãos

**Problemas que a orquestração atual gera:**

1. **Itens presos em processamento** (`PRIORITY_QUEUE_PROCESSING_KEY`)
   - **Causa:** Callback `finalize_processing_requeue` não executa se task falha brutalmente (timeout, SIGKILL)
   - **Sintoma:** Produto não é rechecado até `reclaim_stale_processing(TTL)` recuperá-lo (até 30 minutos padrão)
   - **Risco:** Atrasos críticos em monitoramento

2. **Loop bloqueante com `time.sleep`**
   - **Causa:** `time.sleep(poll_interval)` no loop contínuo bloqueia thread do worker
   - **Sintoma:** Worker monitor não responde a sinais (SIGTERM) imediatamente
   - **Risco:** Deploys lentos, impossibilidade de graceful shutdown

3. **Processamento sequencial no batch**
   - **Causa:** Loop `for _ in range(batch_size)` processa um item por vez
   - **Sintoma:** Lote de 20 itens leva 20 * tempo_médio_scraping; se scraping demora 5s, é 100s de latência
   - **Risco:** Fila fica "atrasada" mesmo com poucos itens

4. **Sem circuit breaker para scraper**
   - **Causa:** Se `market_scraper` cai, cada coleta tenta e falha individualmente
   - **Sintoma:** Centenas de requisições falhando, logs poluídos, retry exponencial acumulando tarefas
   - **Risco:** Sobrecarga do broker Redis com tarefas de retry

5. **Concorrência descontrolada nos competitors**
   - **Causa:** `enqueue_competitors_for_monitored` cria tasks com delay fixo, mas se competitor list é grande (50+ itens), todas chegam na fila em poucos segundos
   - **Sintoma:** Picos de 50+ requisições simultâneas ao `market_scraper`
   - **Risco:** Rate limiting 429, bans de IP em sites alvo

---

#### 4.3 Otimização e Mal Desempenho

**Por que ele atualmente não suporta 24/7?**

1. **Memory leak potencial no loop contínuo**
   - Loop infinito sem limpeza de recursos pode acumular conexões/handles
   - Não há reinício programado do worker monitor
   
2. **Falta de monitoramento de saúde**
   - Sem healthchecks ativos: loop pode travar e ninguém saber
   - Sem métricas: fila pode crescer infinitamente sem alarmes

3. **Redis como ponto único de falha**
   - Se Redis cai: todo sistema para (broker + fila de prioridade + locks)
   - Sem estratégia de fallback ou persistência durável

4. **Sem backpressure**
   - Se scraping fica lento (sites lentos, rate limits), fila de prioridade cresce indefinidamente
   - Não há mecanismo de "pausar" adição de novos itens quando fila está saturada

5. **Lock TTL inadequado**
   - 20s é curto para sites lentos; lock expira durante scraping legítimo
   - Causa coletas duplicadas e desperdício de recursos

**Como está a otimização e desempenho?**

📉 **Gargalos identificados:**

| Componente | Problema | Impacto |
|------------|----------|---------|
| Loop contínuo | Processamento sequencial (1 por vez no batch) | **Alta latência** se batch_size grande |
| Collect task | Lock TTL fixo de 20s | **Coletas duplicadas** em sites lentos |
| Redis | Operações síncronas bloqueantes | **Latência acumulada** em operações de fila |
| ScraperClient | Sem connection pooling (cria novo `httpx.Client` a cada call) | **Overhead de TCP handshake** |
| Competitors | Sem batching inteligente (todos enfileirados de uma vez) | **Picos de carga** no scraper |

**Onde estão os problemas principais relacionados à arquitetura?**

1. **Arquitetura:**
   - **Falta de padrão Event-Driven:** Mudanças de preço disparam comparações dentro da task (acoplamento)
   - **Estado distribuído sem coordenação:** Redis + Postgres sem transações distribuídas; race conditions possíveis
   
2. **Infraestrutura:**
   - **Redis sem replicação:** Ponto único de falha
   - **Sem message queue durável:** Celery com Redis perde mensagens se Redis cai durante processamento
   - **Workers sem autoscaling:** Concorrência fixa; não adapta a carga

3. **Desenvolvimento:**
   - **Logs estruturados incompletos:** Falta correlation IDs consistentes entre tasks
   - **Testes de integração ausentes:** Não há como validar fluxo completo (API → Loop → Scraping → Comparação)
   - **Documentação defasada:** README diz "idempotente" mas implementação não garante isso (race conditions no lock)

---

> **Nota final:** Este sistema está funcionando como um **protótipo avançado tentando operar em produção**. A arquitetura base é sólida (workers dedicados, fila de prioridade, locks distribuídos), mas faltam mecanismos de resiliência, observabilidade e controle de fluxo necessários para operação 24/7 confiável. As melhorias críticas incluem: healthchecks ativos, circuit breakers, backpressure, e migração do loop bloqueante para modelo orientado a eventos.