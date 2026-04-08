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
Criar e alinhar o ambiente de testes do módulo compartilhado shared para validar contratos, utilitários, infraestrutura técnica e clientes de integração, com cobertura consistente de testes unitários e de integração, sem dependência de infraestrutura externa real nos cenários unitários.

**Estratégia de Implementação**  
A implementação será incremental em 4 fases:  
1. fundação do ambiente de teste do shared,  
2. cobertura unitária dos componentes críticos,  
3. integração controlada dos clientes e fluxos entre componentes,  
4. governança de qualidade (execução, cobertura e estabilidade).  
Cada fase terá critérios objetivos para reduzir flakiness e garantir isolamento.

---

## Análise de Riscos e Decisões Chave

**Decisão Técnica Principal**  
Adotar isolamento por nível de teste:  
- Unit: zero I/O real (Redis, Temporal, HTTP, banco), usando monkeypatch, mocks e fakeredis quando necessário.  
- Integration: integração entre componentes do próprio shared com dependências técnicas controladas (stubs/fakes), sem chamar serviços reais do ecossistema.

**Risco Principal**  
Flakiness por dependências de tempo/rede e acoplamento cruzado com módulos de serviço, especialmente nos clientes scraper_client.py e orchestrator_client.py.  
Mitigação: timeout curto em teste, estado global resetado por fixture, fakes determinísticos e cenários de erro explícitos.

**Dependências**  
- Configuração global de pytest em pytest.ini  
- Bootstrap global em conftest.py  
- Contratos canônicos em schemas  
- Componentes de infra em infra  
- Diretrizes arquiteturais em README.md

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
