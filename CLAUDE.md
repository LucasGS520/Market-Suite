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

## Resumo e Estratégia do Plano

- **Problema**: O `market_scraper` está conseguindo navegar e renderizar páginas, mas não está convertendo isso em extração real de dados de produto; na prática, a maior parte das coletas termina em challenge anti-bot, `no_result`, 422 ou timeout 504.

- **Sintoma observado**: Nos logs, a Camada 1 retorna HTML com padrão `mercadolivre_challenge`, a Camada 3 também retorna HTML com challenge residual, e o pipeline encerra sem payload útil.

- **Objetivo da correção**: Fazer o módulo priorizar coleta útil de produto, separando claramente sucesso de navegação de sucesso de extração, e aumentar a taxa de payload válido em páginas de produto.

- **Premissas**
  - O anti-bot do alvo continuará existindo e deve ser tratado como condição recorrente, não como exceção isolada.
  - O contrato HTTP do endpoint deve permanecer compatível.
  - O serviço já tem base técnica suficiente; o problema central é a orientação do fluxo para extração, não apenas navegação.

---

### Riscos, Dependências e Decisões

- **Decisão Técnica Principal**: Reorientar o fluxo para tratar aquisição de HTML como etapa intermediária e extração de dados como objetivo final, com classificação baseada em sinal de produto e não apenas em “HTML obtido”.

- **Risco Principal**: Relaxar demais a régua de qualidade e passar a aceitar payloads fracos ou ambíguos; o ajuste precisa evitar falso positivo de extração.

- **Impacto atual**: Alta taxa de `no_result`, 422 frequente e 504 em parte dos casos; o módulo entrega infraestrutura de navegação, mas baixa entrega de dados úteis.

- **Dependências**
  - fetch_decision_gate.py
  - response_classifier.py
  - pipeline_steps.py
  - parser_runner.py
  - validator.py
  - response_helpers.py
  - routes_scraper.py

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
