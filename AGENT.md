# Contexto Codex — Organização e Separação Modular (`market_orchestrator`)

## Resumo e Estratégia do Plano

**Objetivo:**  
Separar as responsabilidades misturadas no schemas_workflow.py, movendo o `WorkflowState` (Enum) para o diretório `enums/` e dividindo os schemas em arquivos coesos por responsabilidade — alinhando `market_orchestrator` ao padrão que `market_alert` e `market_scraper` já seguem.

**Estratégia de Implementação:**  
Executar em três fases: primeiro definir a arquitetura-alvo congelando contratos; depois mover o Enum; depois dividir os schemas; e por fim atualizar todos os imports de consumidores internos.

---

## Análise de Riscos e Decisões Chave

**Decisão Técnica Principal:**  
Não renomear nenhuma classe ou campo — apenas mover. Todos os contratos públicos (`WorkflowState`, `WorkflowInput`, `CollectionPolicy`, payloads de signal, `WorkflowSnapshot`, `CollectionStatusResult`) mantêm exatamente o mesmo nome de símbolo, garantindo zero regressão nos consumidores externos.

**Risco Principal:**  
Quebra silenciosa de imports no `workflow/` e `activities/` que hoje importam tudo de `schemas_workflow`. Mitigação: mapear todos os pontos de import antes de qualquer mudança e atualizar numa etapa dedicada.

**Risco Secundário:**  
`WorkflowState` é usado como tipo em `schemas_workflow.py` (ex.: `WorkflowSnapshot.state`). Se o Enum for movido antes de o schema ser atualizado, há import circular. Mitigação: mover Enum primeiro, em seguida atualizar `schemas_workflow.py` para importar de `enums`.

**Dependências internas a atualizar:**  
- `workflow/monitored_product_workflow.py`, `workflow/state_handlers.py`, `workflow/signal_handlers.py`, `workflow/query_handlers.py`, `workflow/helpers.py`
- `activities/dispatch_activity.py`, `activities/status_activity.py`, `activities/policy_activity.py`, `activities/snapshot_activity.py`
- `alert/alert_client.py`, `reconciler.py`, `__init__.py`

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
