# Claude — Correção Camada de Inicialização

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

## Objetivo e Problemas a ser Resolvido

- **Problema:** A validação do Temporal durante o startup da API bloqueia e gera `TimeoutError` porque `run_sync_coro` usa `asyncio.run_coroutine_threadsafe(...).result()` quando chamada do mesmo event loop do FastAPI, produzindo deadlock.  

- **Objetivo:** Permitir que `market_alert` valide o Temporal sem bloquear o event loop do FastAPI, preservando comportamento síncrono para Celery e mantendo validação robusta de conectividade.

---

**Análise de Riscos e Decisões Chave**

- **Decisão técnica principal:** Executar a validação de startup da API fora do event loop (thread) é a correção imediata recomendada — mínimo impacto e resolve deadlock.  

- **Risco principal:** Se variáveis `TEMPORAL_HOST`/`TEMPORAL_PORT`/`TEMPORAL_NAMESPACE` estiverem incorretas, a validação continuará falhando mesmo sem deadlock.  

- **Dependências críticas:** Temporal server acessível na rede interna do Docker; envs corretos em `market_alert` (comparar com `market_orchestrator`).

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
