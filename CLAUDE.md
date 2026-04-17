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

### **Objetivo**
Objetivo: fechar os gaps remanescentes sem perder os ganhos já obtidos, levando o fluxo para aderência total ao desenho ideal: previsível, auditável, com sucesso útil maximizado e contrato HTTP preservado.

**Arquivos relevantes**
- routes_scraper.py — Guarda final de sucesso útil e logs de aceite.  
- response_helpers.py — Fonte canônica de utilidade e limpeza de mapeamentos de erro.  
- pipeline_steps.py — Orquestração da segunda chance via browser e guarda anti-loop.  
- fetch_decision_gate.py — Telemetria e reason de escalonamento.  
- parser_runner.py — Consistência da validação de dado útil.  
- validator.py — Regra de utilidade única e previsível.  
- config_scraper.py — Defaults operacionais de robots/rate limiter.  
- conditional_payload.py — Preservação de metadados de qualidade no cache condicional.  
- test_response_helpers.py  
- test_pipeline_steps.py  
- test_fetch_decision_gate.py  
- test_parse_flow.py  
- test_pipeline_integration.py  
- README.md  
- plano_refatoracao_scraper.md

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
