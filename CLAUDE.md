# Claude - Arquitetura Redis + PostgreSQL

Reorganizar e normalizar separação arquitetural e o uso de Redis e PostgreSQL no projeto, para que cada um assuma as responsabilidades ideias, garantindo:
- **PostgreSQL:** Fonte de verdade única para dados persistentes críticos
- **Redis:** Orquestrador de decisões rápidas e cache efêmero (~10ms)
- **Sistema:** Mais resiliente, escalável e com separação clara de concerns

---

## Análise de Riscos e Decisões Chave**

### **Risco Principal**
**Dessincronização entre Cache Redis e Source PostgreSQL**
- Exemplo: `cache:product:123:price = 99.90` mas `monitored_products.current_price = 95.00`
- **Mitigação**: Implementar padrão cache-aside com invalidation explícita e TTL curto

### **Decisão Principal 1: Estratégia de Cache**
- **Opção A** (Recomendado): Cache-Aside com Invalidation
  - PostgreSQL é sempre source
  - Redis cache é "nice-to-have", pode estar stale
  - Invalidar ao escrever em DB
  - TTL como fallback
- **Opção B** (Não recomendado): Write-Through
  - Melhor consistência, mas mais lento
  - Complexidade maior

**Decisão**: Usar **Cache-Aside** (Opção A) — alinha com velocidade

### **Decisão Principal 2: TTL por Categoria**
- **Rate limiting**: 60-3600s (janela de coleta)
- **Locks**: 20-60s (duração de task)
- **Cache dados**: 300-900s (preço, comparação)
- **Robots.txt**: 3600s (1h, muda pouco)
- **Idempotência**: 300s (5 min, curto por segurança)

### **Decisão Principal 3: Segregação de Chaves**
- Usar prefixos explícitos: `lock:`, `rate:`, `cache:`, `circuit:`, `idemp:`, `robots:`
- Documentar padrão de chave em cada módulo

### **Risco Secundário**
**Perda de dados ao deletar cache Redis**
- Se você fizer `FLUSHALL`, perde todos locks ativos
- **Mitigação**: Scripts de clear seletivo por padrão (ex: `SCAN cache:*`)

---

## **Resultado e valor agregado ao executar o plano**
- **Melhor performance e escala:** reduz carga de leitura/gravação no Postgres ao servir dados voláteis via Redis (dashboard e caches), melhorando latência e throughput.
- **Clareza de responsabilidade:** PostgreSQL vira fonte única de verdade para dados persistentes; Redis centraliza apenas estado transitório, locks e decisões em tempo real — menor risco de inconsistência.
- **Resiliência previsível:** fallback documentado (o que acontece se o Redis cair) evita comportamento indefinido e facilita runbooks operacionais.
- **Manutenção e observabilidade:** chaves, TTLs e padrões padronizados tornam debugging, métricas e tuning mais simples (hit-rate, keys growth).
- **Custo operacional controlado:** evita armazenar dados históricos em RAM e permite dimensionar Redis para memória curta/rápida e Postgres para disco/consultas.

**Pontos e funcionalidades diretamente afetadas**
- Redis (alterações/normalização e uso):
  - Config e TTLs: `config_base.py`  
  - Cliente/utis Redis: `redis_client.py`  
  - Locks distribuídos: `redis_locks.py`  
  - Idempotência: `idempotency.py`  
  - Pub/Sub (sem mudança de broker agora, apenas documentação): `redis_pubsub.py`  
  - Rate limiter / scripts Lua: `rate_limiter.py` e `backend/shared/infra/redis/redis-scripts/sliding_window.lua`
  - robots.txt cache (migrar de memória local → Redis): `robots.py`
  - Novos módulos a criar: `shared/infra/cache_strategy.py`, `shared/enums/cache_keys.py`, `shared/utils/cache_invalidator.py`
- PostgreSQL (garantir source of truth e otimizar):
  - Modelos e índices: `models_products.py`, `models_price_history.py`, `models_comparisons.py`
  - Migrações Alembic para índices (nova migration em versions)
- Fluxos afetados (código que executa lógica):
  - Coleta/scraping: `collector_product_task.py`
  - Cliente de scraping / circuit breaker: `scraper_client.py` e `circuit_breaker.py`
  - Comparações e notificações (caching e invalidação) — serviços em `market_alert/comparisons/` e `market_alert/notifications/`

**3) Impacto na situação atual do projeto**
- Curto prazo (migração/implementação):
  - Trabalho invasivo moderado: mudanças em utilitários Redis, introdução de cache-strategy e pequenas alterações em pontos de leitura/escrita (hooks de invalidation).
  - Risco operacional: se TTLs ou invalidations não forem aplicados corretamente, haverá staleness; mitigação com testes e rollout por etapas.
  - Coordenação necessária: atualizar configurações em `shared/core/config_base.py` e comunicar times (deploys, feature-freeze parcial durante migrações críticas).
- Médio prazo (após conclusão):
  - Menor latência nas leituras frequentes (dashboards, endpoints públicos).
  - Menor carga no Postgres para consultas de leitura recorrentes.
  - Mais previsibilidade em comportamento quando Redis está indisponível (fórmulas de fallback já definidas).
- Não afetado nesta etapa:
  - Configuração do Redis como broker/Celery (conforme requisitado, será tratada em etapa separada).

---

## Regras e Instruções de Execução
**Regras obrigatórias de economia (NÃO IGNORAR)**
1) NÃO liste árvore inteira do projeto (evite `tree`, `ls -R`, etc.). Se precisar, liste apenas pastas-alvo da FASE.
2) NÃO leia arquivos completos. Leia no máximo 120 linhas por arquivo (ou trechos específicos). Se precisar de mais contextualização, peça antes.
3) Priorize busca (rg/grep) para localizar pontos de mudança antes de abrir arquivos.
5) Não cole conteúdo integral de arquivos na resposta. Mostre apenas:
   - arquivos alterados
   - resumo do diff (o que mudou e por quê)
   - comandos executados e resultados
6) Execute somente UMA FASE por vez. Ao terminar a FASE:
   - pare e peça autorização para a próxima FASE
7) Se detectar duplicação/overreach fora do escopo, interrompa e reporte.
