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

## Resumo do Problema e Objetivo da Correção

- **Problema:** O `market_scraper` está arquiteturalmente organizado, mas ainda opera com desalinhamentos práticos em coleta anti-bot, tempo de falha, identidade de sessão e coerência de headers, o que leva a timeouts longos e respostas `503/504` quando o alvo está hostil.

- **Sintoma observado:** Em VPS/staging, o fluxo entra em challenge anti-bot, o browser permanece por tempo excessivo, aparecem `browser_handler_orphan` e o endpoint encerra em `503/504` sem HTML confiável para a extração. Isso está documentado no diagnóstico atual em diagnostico_atual_scraper.md e nos logs em scraper_stag.log.

- **Objetivo da correção:** Alinhar o módulo ao comportamento ideal descrito em regras_scraper_ideal.md e estrutura_ideal_sessao_headers_scraper.md, mantendo os serviços e camadas existentes, com foco em falha rápida, sessões consistentes, headers coerentes e operação legítima em dados públicos.

---

## Riscos, Impacto e Decisões

- **Decisão Técnica Principal:** Manter a arquitetura atual e ajustar o comportamento operacional para tratar anti-bot, sessão e headers como política de execução, não como lógica manual espalhada. A identidade deve continuar centralizada no runtime/Crawlee, com coerência entre camada HTTP e browser, sem inventar gerenciadores próprios de fingerprint, cookies ou headers.

- **Risco Principal:** Ajustar sessão, headers e budgets pode alterar a taxa de sucesso, os códigos retornados e a semântica de alguns erros já consumidos por integrações existentes.

- **Impacto atual:** Alto custo de tempo por tentativa, 504 tardio, pouca previsibilidade em VPS/staging, desperdício de recurso em challenge pages e diagnóstico ambíguo entre bloqueio terminal e lentidão legítima.

- **Dependências**
  - Propriedades já existentes em config_scraper.py para budgets, policy e sessão.
  - Runtime atual em crawlee_runtime.py, http_collector.py e browser_collector.py.
  - Taxonomia de erro em errors_map.py.
  - Regras idealizadas em regras_scraper_ideal.md e estrutura_ideal_sessao_headers_scraper.md.

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
