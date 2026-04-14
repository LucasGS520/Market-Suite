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

- **Problema:** O alinhamento semântico entre coleta, orquestrador e comparação avançou, mas a visibilidade contratual para a UI ainda é insuficiente, mantendo produtos em estado ambíguo como “Coletando dados...” mesmo quando já existe falha classificada.

- **Sintoma observado:**
  - Nos logs de staging, a coleta já classifica corretamente falhas como error com reason tipado, por exemplo http_429 e scraper_unavailable, com source_integrity false e semantic_category transient.
  - A UI continua dependente de heurística fraca para estado de coleta, baseada em ausência de last_scraped_at e preço nulo, sem consumir motivo/estado contratual explícito: productStatus.ts.
  - A mensagem “Coletando dados...” é exibida sem vínculo com reason e next_retry_at: renderMonitoredPrice.tsx.

- **Objetivo da correção:** Criar Testes que cubram o contrato ponta a ponta para que estado de coleta, motivo e próxima ação sejam persistidos e exibidos de forma explícita ao usuário, eliminando ambiguidade operacional.

- **Premissas:**
  - Catálogo semântico central já existe e deve ser a fonte única: `collection_catalog.py`.
  - Classificação de falhas no coletor já está funcional em staging.
  - O problema restante é majoritariamente de propagação e apresentação contratual.

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
