# Claude — Contexto e Objetivos

## Sobre o Projeto *Market Suite* (`market_suite`)
**MarketSuite** é uma plataforma de monitoramento e comparação de preços em e-commerce. Usuários cadastram produtos que desejam acompanhar, o sistema coleta informações de preço e disponibilidade automaticamente, compara com concorrentes e dispara notificações quando mudanças significativas são detectadas.

O projeto é separado por responsabilidades, em diferentes módulos:
**Backend**:
- **API + Persistência** (market_alert): Gerencia estado de usuários, produtos, comparações
- **Scraping especializado** (market_scraper): Extrai dados de e-commerce via HTTP
- **Processamento em background** (Celery + Redis): Coleta, comparação e notificações assíncronas
- **Orquestração durável** (market_orchestrator): Ciclo de vida contínuo de monitoramento por produto com Temporal.

**Frontend**:
- **SPA moderna**: consome API backend via HTTP (REST/JSON).

> Informações sobre a Stack e Tecnologias existentes em [STACK_MARKET.md](STACK_MARKET.md)

---

### Resumo do Problema e Objetivo da Correção

- **Objetivo:** Alinhar e robustecer o contrato entre coleta, orquestrador e comparação, preservando a arquitetura atual e corrigindo ambiguidades semânticas para distinguir falha transitória, falha estrutural e ausência real de resultado.

- **Resultado Esperado:** Taxonomia única e versionada de outcome/reason aplicada de ponta a ponta, com decisões do workflow mais precisas e resumos de comparação refletindo falhas upstream de forma explícita.

- **Estratégia de Execução:** Implementar por camadas sem quebrar contratos externos: primeiro catálogo semântico único, depois adaptação de classificação no coletor, em seguida leitura no status/orquestrador, e por fim propagação para comparação/observabilidade.

- **Premissas:**
  - Contrato base já está estável: payload tipado e retorno com outcome/status/reason/next_retry_at/product_id.
  - Gating por `persisted_at` já está correto e deve ser preservado.
  - Correções devem priorizar compatibilidade retroativa.

- **Pontos em Aberto** (se houver)
  - Definir política final de retry para erros estruturais de página (sempre retryável, parcialmente retryável, ou não retryável por domínio/host).
  - Definir se `source_integrity` será campo explícito no ScrapeResult ou derivado internamente por regra.
  - Definir granularidade mínima obrigatória de reason para dashboards (por exemplo, dom_not_ready e selector_missing separados ou agrupados em parse_structure_error).

---

### Riscos, Impacto e Decisões

- **Decisões Técnicas Principais**
  - Criar catálogo único de semântica (outcomes, reasons, classes de erro, retryabilidade, neutralidade para workflow) em módulo compartilhado.
  - Proibir strings soltas para outcome/reason em coleta, status activity e workflow; usar apenas constantes/enums do catálogo.
  - Redefinir `no_result` como exclusivo de ausência legítima de dado após resposta íntegra e parse válido.
  - Reclassificar anti-bot/challenge/timeout/bloqueio para outcome error com reason tipado.
  - Manter compatibilidade de payload e envelope atuais, adicionando metadados semânticos progressivamente.

- **Riscos Principais**
  - Regressão por mudança de significado em métricas e alertas existentes.
  - Divergência entre implementação e comentários/documentação (caso lock_exhausted vs lock_skipped).
  - Classificação excessivamente rígida gerar falsos erros em páginas limítrofes.
  - Comparação passar a “silenciar” cenários se upstream_reason não for propagado corretamente.

- **Dependências**
  - Coletor: `collector_product_task.py`
  - Normalização de resultado: `collector_result.py`
  - Contratos compartilhados: `shared_schemas_orchestrator.py` e `shared_schemas_scraper.py`
  - Leitura de status: `status_activity.py`
  - Workflow: `workflow.py`
  - Gating comparação: `price_comparator.py`
  - Serviço de comparação: `services_comparison.py`

- **Impactos Arquiteturais** (se aplicável)
  - Sem impacto estrutural relevante; impacto principal é semântico e de governança de contrato.
  - Melhora de observabilidade operacional e redução de ambiguidade de backoff no workflow.

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
