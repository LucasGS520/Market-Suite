# Contexto Claude — Orquestrador Contínuo com Temporal (`market_orchestrator`)

## Resumo e Estratégia do Plano

**Objetivo:** Implementar o módulo `market_orchestrator` como um serviço de Workflow Durável baseado em Temporal, criando um plano de controle que governa o ciclo de vida contínuo de cada monitoramento ativo — sem reescrever a camada de execução existente (Celery, scraper, comparação, notificações).

**Estratégia de Implementação:** A implementação será executada em **fases sequenciais**. Começamos pela infraestrutura (Temporal Server + SDK), depois construímos a fundação do módulo (workflow + activities + worker + reconciliador + cliente), em seguida integramos os pontos de adaptação já preparados no código (`TODO`s e no-ops), adicionamos observabilidade corrigida, e finalizamos com testes e validação operacional.

---

## Análise de Riscos e Decisões Chave

**Decisão Técnica Principal:** Adotar o SDK oficial `temporalio` (Python) como biblioteca de workflow, mantendo o Celery/Redis como camada de execução de tasks pesadas. O workflow orquestra; o Celery executa. O banco Temporal opera em instância PostgreSQL separada, sem tocar o banco de negócio.

**Risco Principal:** **Não-determinismo no código do Workflow.** Se qualquer I/O, relógio do sistema (`datetime.now()`), UUID aleatório ou import de infra vazar para dentro da classe Workflow (fora de uma Activity), o replay do histórico será corrompido e o workflow falhará de forma silenciosa e difícil de debugar.

**Risco Secundário:** **Fallback durante transição.** Nos ambientes onde o Temporal ainda não estiver disponível (ex: desenvolvimento local sem o profile `temporal`), as chamadas ao `TemporalClient` devem falhar de forma não-bloqueante e logar o erro — jamais interrompendo a operação de domínio já testada (`enqueue_collect` direto).

**Dependências:**
- Temporal Server (novo serviço Docker) + `temporalio` Python SDK (nova dependência no requirements-base.txt).
- PostgreSQL dedicado para o Temporal (instância separada no `docker-compose.yml`).
- Contrato estável da task Celery `market_alert.collectors.tasks.collector_product_task.collect_product_task` — não pode mudar.
- `enqueue_collect()` e `CollectionEnqueuer` em `collector_service_orchestrator.py` e `enqueuer.py` — preservados como ponto de enfileiramento.

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
