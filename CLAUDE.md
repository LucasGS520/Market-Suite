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

### Resumo e Estratégia do Plano

- **Objetivo:** Fechar contratos entre os módulos de scraping/coleta/orquestração, eliminar ambiguidades de responsabilidade e impedir vazamento de domínio durante a evolução do serviço de scraping (`market_scraper`).

- **Resultado Esperado:** Fronteiras técnicas explícitas e testadas entre market_scraper, market_alert e market_orchestrator, com contratos versionados e matriz de responsabilidades validada.

- **Estratégia de Execução:** Executar em fases curtas e verificáveis: governança de domínio -> contrato técnico -> semântica de erros -> observabilidade -> testes de contrato -> gates de mudança.

- **Premissas:** O fluxo atual já está funcional na orquestração; o problema principal é consistência contratual e governança entre módulos, não ausência de componentes.

---

### Riscos, Impacto e Decisões

- **Decisões Técnicas Principais**
- Consolidar contrato de entrada/saída do scraper em torno de `shared_schemas_scraper.py` e `routes_scraper.py`.
- Consolidar semântica de coleta em `collection_catalog.py` e mapeamento em `collector_result.py`.
- Manter responsabilidade de extração no scraper, política operacional de coleta no alert e transição de estado no orchestrator.

- **Riscos Principais**
- Divergência entre `error_code` emitido pelo scraper e `reason` usado pelo coletor.
- Duplicação de retry/backoff em camadas diferentes gerando comportamento imprevisível.
- Regressão silenciosa por ausência de testes de contrato ponta a ponta.

- **Dependências**
- Contratos compartilhados em schemas.
- Cliente consumidor em `scraper_client.py`.
- Activities de status/dispatch em `status_activity.py` e `dispatch_activity.py`.

- **Impactos Arquiteturais**
- Redução de acoplamento implícito.
- Maior previsibilidade de evolução do scraper sem quebrar coleta/orquestração.
- Melhoria de diagnósticos operacionais por padronização de sinais entre serviços.

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
