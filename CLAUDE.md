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

- **Objetivo:** Reestruturar o módulo `market_scraper` para uma arquitetura simples, modular, auditável e determinística, reduzindo sobreposição de responsabilidades e mantendo compatibilidade total do contrato público.

- **Resultado Esperado:** Fluxo de scraping organizado em camadas rígidas (HTTP/Contrato, Orquestração, Coleta, Parsing, Pós-processamento, Infra), com cadeia de parsing fixa, escalonamento controlado HTTP→Browser, telemetria obrigatória consistente e previsibilidade de comportamento em sucesso/falha.

- **Estratégia de Execução:** Executar migração incremental com feature flags e “strangler pattern” (novo fluxo convivendo com o legado até estabilização), validando contrato e comportamento em cada fase com suíte de testes de contrato, integração e cenários críticos.

---

### Riscos, Dependências e Decisões

**Decisões Técnicas Principais**
  - Migração incremental com **compatibilidade externa congelada**.
  - Introdução de **camada Application/UseCase** para centralizar fluxo determinístico e tirar lógica da rota.
  - **Coleta como etapa fechada** antes da extração; proibida reentrada tardia de browser dentro da cadeia de parsing.
  - `FetchDecisionGate` mantido, mas reduzido a política de coleta (não orquestrador geral).
  - Telemetria obrigatória produzida a partir de DTO de coleta/execução, sem depender de dicionário aberto.
  - Reorganização estrutural: coleta em `services/http` e `services/browser`, infra em `infrastructure/*`, mapeadores/resposta em utilitários explícitos.
  - `response_helpers` fatiado em responsabilidades únicas (`error_mapper`, `response_mapper`, `response_builder`).
  - `validator`, `availability_inference` e trechos de runner convergem para pós-processamento único.
  - Descontinuação de `LateBrowserEscalationStep` e eliminação gradual do uso central de `PipelineContext.data`.

**Riscos Principais**
  - Regressão silenciosa de contrato/semântica HTTP durante refatoração interna.
  - Queda de taxa de extração útil por mudança na ordem/heurística de parsing.
  - Aumento de latência no fallback browser e impacto em throughput.
  - Complexidade de convivência entre fluxo legado e novo durante migração.
  - Acoplamento excessivo caso Crawlee entre no núcleo, em vez de adaptador.
  - Remoção precoce do legado sem critérios objetivos de estabilidade.

**Dependências**
  - Dependências técnicas atuais: `curl_cffi`, `playwright`, parsers (extruct/parsel/bs4/lxml), Redis.
  - Instrumentação de logs estruturados com `trace_id` e correlação.
  - Feature flags para roteamento de fluxo (legado vs novo) e rollout gradual.

**Impactos Arquiteturais**
  - Redução de acoplamento entre API, coleta e parsing.
  - Aumento de previsibilidade por fluxo linear e política explícita.
  - Melhor testabilidade por camadas com entradas/saídas fechadas.
  - Menor dispersão de regra de negócio em helpers genéricos.
  - Base pronta para evolução futura (proxy/crawlers adicionais) sem inflar o orquestrador.

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
