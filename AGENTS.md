# Contexto Codex — Organização e Separação Modular (`market_orchestrator`)

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

## Objetivo e Estratégias de Implementação

**Objetivo**  
Criar e alinhar um ambiente de testes técnico e automatizado para o módulo `market_alert`, cobrindo testes unitários e de integração dos fluxos essenciais de autenticação, usuários, produtos, coleta, comparações, notificações, segurança e startup operacional.

**Estratégia de Implementação**  
A implementação será feita em 6 fases sequenciais: fundação do ambiente, padronização da estrutura de testes, suíte unitária por domínio, suíte de integração por fluxos críticos, testes de estresse técnico, e governança contínua por qualidade e execução em CI.  
A abordagem prioriza:
- Isolamento para testes unitários.
- Integração realista para fluxos críticos.
- Observabilidade, segurança e determinismo desde o início.

---

## Análise de Riscos e Decisões Chave

**Decisão Técnica Principal**  
Adotar pirâmide de testes com duas trilhas explícitas:
- Unit: validação de regras puras e serviços com mocks/fakes.
- Integration: validação de contratos e fluxos fim-a-fim do backend com infraestrutura de teste controlada.

**Risco Principal**  
Flakiness por dependências externas e estado compartilhado (DB/Redis/Temporal/Celery), causando falsos negativos e baixa confiança.

**Mitigações Principais**
- Fixtures com isolamento por teste e limpeza transacional.
- Fakes e mocks para integrações externas em unit.
- Marcadores e execução segregada por suíte.
- Timeouts, retries e seeds determinísticas.

**Dependências**
- Estrutura recomendada em `estrutura_ambiente_testes.md`.
- Contratos e fluxos documentados em `README.md`.
- Configuração da aplicação em `config_alert.py`.
- Bootstraps e runtime operacional em `main.py`, `startup_validation.py`, `celery_app.py`.

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
