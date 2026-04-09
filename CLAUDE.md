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

## Diagnóstico Principal
A orquestração foi executada (Temporal + Redis OK) e dispatchs foram gravados, porém as tasks de coleta que deveriam persistir resultados falham em runtime dentro do worker Celery devido a um `AttributeError` referente a `RetryPolicy.SCRAPE_RETRY_WINDOW_SECONDS`. Como consequência direta, não há gravação em `price_history` nem atualização de `last_scraped_at`.  
  
  - **Fatos que sustentam essa conclusão:**
    - `dispatch_collection_ok` aparece nos logs do orquestrador para o `monitored_id` (orquestrador fez o trabalho de enfileirar/dispatch).  
    - Redis contém `workflow:dispatch` e `workflow:snapshot` para o monitorado — indica dispatch registrado.  
    - Worker Celery reportou exceção explícita `AttributeError(...)` durante execução de `collect_product_task` — indica falha em processamento.  
    - DB mostra `last_scraped_at` nulo e `price_history` vazio para o monitorado — resultado esperado quando task falha antes de persistir.

---

## Conclusões e Objetivo

- `market_alert` recebeu requisição e enfileirou.
- `market_orchestrator` está vivo e faz dispatch (confirmado antes por `dispatch_collection_ok` e chaves `workflow:*`).
- `celery-worker-scraping` recebe e executa tasks.
- Falha ocorre **na lógica de execução/retry da task**, não na infraestrutura base (Redis/queues/worker up).

Corrigir e Ajustar problemas de falha de código, quebra de tasks de coletas para que requisições recebidas pelo orquestrador retorne dados corretos e processamento correto de execução.

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
