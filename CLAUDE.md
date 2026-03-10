# Claude — Consolidação Celery + Redis

## Resumo e Estratégia do Plano

### Objetivo
Implementar decisões consolidadas sobre Celery e Redis para transformar a infraestrutura assíncrona e operacional do `market_alert` em um estado **totalmente endurecido, isolado logicamente e com fronteiras claras**, pronto para as fases posteriores de desenvolvimento.

### Estratégia de Implementação
O plano será executado em **fases sequenciais**, cada uma validável independentemente, mas com dependências explícitas:

1. **Preparação** — Inventário de arquivos afetados e planejamento técnico
2. **Configuração Celery** — Decisões 1, 2, 7 (pool, robustez, retry)
3. **Isolamento Redux** — Decisão 5 (separação db 0/1/2)
4. **Locks, TTL e Namespacing** — Decisões 3, 4 (rate limit, TTL)
5. **Idempotência e Contratos** — Decisão 6 (semântica por domínio)
6. **Hardening Operacional** — Decisão 9 (memória, persistência), monitoring, testes

---

## 2. Análise de Riscos e Decisões Chave

### Decisão Técnica Principal
Usar **isolamento de DBs Redis combinado com prefixação de chaves por camada** como padrão de governança operacional. Isso reduz risco de interferência entre broker Celery, result backend e estado operacional sem exigir instâncias Redis separadas (reduz complexidade operacional imediata).

### Risco Principal: **Interrupção Operacional Durante Transição**
A mudança de pool **prefork → gevent** para scraping e a separação de DBs Redis são operações que podem causar perda de tarefas ou deadlock se não coordenadas corretamente.

**Mitigação:**
- Rollout em janelas pequenas com feature flags (se possível, ou pausas de tráfego controladas).
- Draining explícito de filas antes de restarts.
- Validação de compatibilidade de gevent com bibliotecas de scraping antes do merge.
- Testes de failover localistas e em staging idêntico a produção.

### Riscos Secundários

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Conflito de TTL entre lock (60s) e task (45s) | Baixa | Alto | Validação com duração real de tasks |
| Gevent incompatível com cliente HTTP | Média | Alto | PoC isolado antes de merge |
| Perda de mensagens se Redis encher | Média | Alto | `noeviction` obrigatório + monitoring de memória |
| DLQ crescer sem consumo definido | Alta | Médio | Será tratado pós-esta fase |

### Dependências Externas
- Redis estável com Streams habilitado (já disponível).
- Docker e Docker Compose up-to-date.
- Acesso a ambiente de staging idêntico a produção.
- Validação de afinidade de plataforma (gevent + scraping libs).

---

### Resultado Esperado
- Celery opera com 3 workers em pools ajustados, nenhum com fallback de concorrência.
- Redis tem 3 DBs lógicos completamente isolados (broker, result, operacional).
- Todos os locks, rate limiting e cache usam prefixos declarados em config.
- TTLs são definidos e validados contra duração real de tasks.
- Cada task tem contrato claro de semântica (at-least-once ou exactly-once).
- DLQ stream está pronto para consumo (infra OK, apenas consumidor adiado).
- Sistema aguenta carga moderada (50 coletas concorrentes) sem memory leak, deadlock ou perda silenciosa.

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
