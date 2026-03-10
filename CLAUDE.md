# Claude - Reorganização Celery + Redis do `market_alert`

## Objetivo
Reorganizar a arquitetura assíncrona para que:
- Celery opere apenas como orquestrador de tarefas discretas (3 workers puros).
- Redis tenha fronteiras claras por camada lógica (broker/backend, operacional do loop, cache/rate-limit/idempotência).
- DLQ seja orientada a eventos em Redis Streams.
- Loop contínuo saia do fluxo do Celery e fique isolado em módulo próprio, preparando evolução futura para serviço standalone.
- Configuração de Celery passe a respeitar variáveis de ambiente oficiais.

---

### Análise de Riscos e Decisões Chave

**Decisão Técnica Principal**  
Usar Redis Streams como DLQ de falhas permanentes (`celery:dlq`) com consumo por consumer group dedicado para processamento observável e desacoplado.

**Risco Principal**  
Interrupção operacional durante transição do loop contínuo e da DLQ (perda de eventos, dupla execução, ou lacunas de monitoramento).

**Mitigação**
- Rollout em etapas com feature flags por componente.
- Janela de coexistência controlada (old/new) apenas quando necessário.
- Testes de integração com Redis real e cenários de falha.
- Runbook de rollback por fase.

**Dependências**
- Redis estável (Streams habilitado e monitorável).
- Docker Compose/K8s com serviços ajustados.
- Time de observabilidade para métricas e alertas.
- Validação de contratos de tracing (`trace_id`) e idempotência.

**Execução:** Eliminar `task_failures` e usar apenas stream + retenção + exportação.

---

### Resultado Esperado

- Celery opera com 3 workers focados (scraping, compare, notifications) sem loop contínuo acoplado.
- DLQ está em Redis Streams com consumer group ativo e monitorado.
- Configuração Celery respeita CELERY_BROKER_URL e CELERY_RESULT_BACKEND.
- Fronteiras de Redis estão documentadas e aplicadas por prefixo/camada.
- Loop contínuo está isolado em módulo independente, pronto para futura migração tecnológica.

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
