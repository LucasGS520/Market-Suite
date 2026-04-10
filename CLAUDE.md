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

- **Problema:** A esteira de coleta/orquestração funciona, mas sofre degradação por contenção de lock, corrida entre coleta e comparação, e instabilidade de execução de workflow tasks (deadlock/timeout/task-not-found), com risco de repetição em Dev e Staging.

- **Sintoma observado:** Eventos recorrentes de `TMPRL1101`, `TMPRL1104`, `Task not found`, `lock_skipped` com retries, comparação iniciando sem dados consolidados, e sinais operacionais de pressão (`SIGKILL`, deadlines de fila).

- **Objetivo da correção:** Restaurar previsibilidade da execução assíncrona, separar falhas transitórias de falhas finais, reduzir cascata de erros e garantir que a comparação só rode com estado de coleta consistente.

- **Premissas:**
  - O mesmo código-base é promovido entre Dev e Staging.
  - Parte dos ruídos de `watchfiles` é específica de Dev local com `--reload`.
  - Deadlock/timeout/task-not-found e corrida de domínio podem aparecer em qualquer ambiente sob mesma lógica e carga.

---

### Riscos, Impacto e Decisões

- **Decisão Técnica Principal:** Estabelecer contrato explícito de execução assíncrona por estado (`success`, `not_modified`, `retryable_lock`, `retryable_timeout`, `no_result`, `error_final`) e alinhar o gating da comparação para somente após persistência válida.

- **Risco Principal:** Mitigações parciais mascararem sintomas sem resolver causa de coordenação, mantendo degradação intermitente.

- **Impacto atual:** Perda de previsibilidade, janelas com comparação sem candidatos válidos por timing, aumento de retries e risco de queda de throughput sob pressão.

- **Dependências:**
  - Configurações de Temporal (timeouts e comportamento de workflow task).
  - Configurações de Celery (concurrency, prefetch, time limits, backoff).
  - Contratos entre coleta e comparação (persistência e sinalização).
  - Observabilidade comum entre API, workers, orquestrador e temporal.

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
