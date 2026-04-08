# Contexto Codex

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
Alinhar e fechar as lacunas das suítes de testes dos 4 módulos backend para que a cobertura reflita as responsabilidades reais de negócio e infraestrutura, reduzindo risco sistêmico em fluxos assíncronos, integrações e componentes compartilhados.

**Estratégia de Implementação**  
A execução será incremental em fases, priorizando primeiro os pontos de maior risco operacional: tasks assíncronas e infraestrutura compartilhada. Depois, faremos hardening dos módulos já maduros.

---

## Análise de Riscos e Decisões Chave

**Decisão Técnica Principal**  
Adotar matriz de testes por criticidade:  
- Unit: zero I/O real, uso de fakes determinísticos  
- Integration controlada: contratos e fluxos entre componentes locais  
- Integration high-cost: Temporal e fluxos mais caros, com escopo reduzido  
- Stress técnico: somente cenários onde concorrência/timeout é responsabilidade funcional

**Risco Principal**  
Falsa sensação de cobertura por excesso de integração mockada, sem validar pontos de borda críticos (Celery, Redis avançado, dedup/lock/cooldown).  
Mitigação: criar suíte mínima obrigatória por risco operacional e gate de cobertura por área crítica.

**Dependências**  
- Configuração global em `pytest.ini` e `conftest.py`  
- Estrutura alvo em `estrutura_ambiente_testes.md`  
- Requisitos de cada módulo (arquivos requirements)  

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
