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

- **Problema:** O `market_scraper` continua estruturalmente correto, mas operacionalmente frágil principalmente em VPS/staging, com bloqueio anti-bot terminal, fallback browser lento, ausência de proxy efetivo no ambiente e timeouts longos que degradam o endpoint síncrono.

- **Sintoma observado:** Nos logs de scraper_stag.log, o fluxo ainda alterna entre `anti_bot_blocked` e `playwright_timeout`, com tentativas longas, `browser_handler_orphan`, `SessionError` 429 e respostas finais `503/504`.

- **Objetivo da correção:** Transformar o módulo em scraper operacional com coleta resiliente, estados finais explícitos, falha rápida para anti-bot, política de robots clara, diferenciação semântica entre indisponibilidade e bloqueio.

---

## Riscos, Impacto e Decisões

- **Decisão Técnica Principal:** Fechar contratos de estado e endurecer a camada de coleta para anti-bot, priorizando falha rápida e classificação correta, em vez de insistência longa com timeout genérico, passar de “fallback browser que insiste até timeout” para “coleta orientada a bloqueio terminal, identidade e falha rápida”.

- **Risco Principal:** Introdução de proxy/sessão/novos estados alterar comportamento esperado por consumidores atuais da API e por automações que dependem de 422/504.

- **Impacto atual:** Alto custo operacional por tentativas longas, baixa taxa de sucesso em VPS/staging, diagnóstico ambiguo em parte dos erros e baixa previsibilidade de SLA, o sistema ainda desperdiça tempo em challenge pages, produz 504 tardio e mascara bloqueio anti-bot como indisponibilidade temporária.

- **Dependências:** Provedor de proxy com saída BR, variáveis de ambiente válidas por ambiente, observabilidade ativa, suite de testes de regressão e integração em staging.

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
