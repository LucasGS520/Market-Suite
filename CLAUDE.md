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

### **Objetivo**
Transformar o módulo `market_scraper` de uma arquitetura complexa e dispersa (com coexistência de fluxos legado/novo, responsabilidades sobrepostas e múltiplos caminhos de decisão) para uma arquitetura simples, modular e determinística.
1. Módulo reorganizado em 6 camadas explícitas com responsabilidades rígidas e sem sobreposição
2. Fluxo canônico único: validação → coleta finalizada → extração em cadeia fixa → pós-processamento → resposta HTTP
3. Ferramentas obrigatórias (Crawlee, curl_cffi, Playwright, Extruct, Parsel, BS4+lxml) integradas coesivamente
4. Compatibilidade total com contrato externo mantida

**O que está bem alinhado com o espelho ideal `regras_scraper_ideal.md`**

- Fluxo canônico determinístico está implementado no caso de uso, com sequência clara de coleta → extração → pós-processamento → resposta: `parse_product.py`
- Cadeia fixa de extração na ordem exigida (extruct → parsel → bs4+lxml): `extraction_chain.py`
- DTOs fechados e tipados entre camadas: `dtos.py`
- Taxonomia de erro centralizada e mapeamento canônico: `errors_map.py`
- Telemetria estruturada por estágio com trace_id/domain: `telemetry_service.py`, `parse_product.py`
- Cache condicional HTTP (ETag/Last-Modified/304) preservado: `conditional_payload.py`, `routes_scraper.py`
- Integração das ferramentas obrigatórias está presente no módulo:
  - Crawlee + curl impersonation + Playwright: `requirements-market-scraper.txt`
  - Uso na coleta: `http_collector.py`, `browser_collector.py`

---

**Diagnóstico de aderência (estado atual x espelho ideal)**

- Regras, comportamento e fluxo de scraping: **alto alinhamento**
- Arquitetura em camadas e contratos: **alto alinhamento**
- Integração de ferramentas obrigatórias: **alto alinhamento**
- Infra operacional “delegar vs customizar”: **alinhamento parcial** (principal gap)
- Resultado geral: **módulo bem próximo do alvo ideal, com desvios pontuais concentrados na camada operacional de coleta**

---

**Perguntas abertas para fechar aderência total**
1. A decisão arquitetural é manter stealth e bloqueio de recursos manualmente no coletor browser, ou migrar isso para configuração mais nativa do runtime Crawlee? R: Migrar isso para configuração mais nativa do runtime Crawlee
2. O loop de retry do HTTP collector deve permanecer como política de produto explícita, ou virar configuração do crawler/runtime para reduzir código operacional próprio? R: Virar configuração do crawler para reduzir código operacional próprio
3. A rota deve passar a usar a fachada de orquestração para consolidar uma única porta interna? R: sim, consolidar única porta interna

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
