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
Implementar um ambiente de testes técnico, automatizado e confiável para o módulo `market_scraper`, cobrindo testes unitários, de integração e técnicos, com foco em validação de regras de parsing, fluxo HTTP, cache condicional, robustez de rede e mapeamento de falhas.

**Estratégia de Implementação**  
A execução será em fases incrementais: primeiro fundação do ambiente e isolamento, depois cobertura unitária dos componentes críticos, em seguida integração de fluxos ponta a ponta internos do módulo, e por fim governança de qualidade (cobertura, estabilidade e execução contínua).  
Cada fase termina com critérios objetivos de validação para reduzir flakiness e evitar acoplamento com infraestrutura externa real.

---

## Análise de Riscos e Decisões Chave

**Decisão Técnica Principal**  
Separar claramente as suítes por nível de isolamento: unit sem I/O real, integration com infraestrutura controlada (fakes e stubs determinísticos), e stress técnico com carga limitada e repetível.

**Risco Principal**  
Flakiness por dependências de rede, tempo e concorrência (download, DNS, robots, cache e singleflight).  
Mitigação: monkeypatch em pontos de I/O, limites de timeout curtos em teste, dados de entrada fixos, reset de estado global por teste e ausência de chamadas externas reais.

**Dependências**  
- Contratos de request/response compartilhados com o módulo shared  
- Configuração carregada por variáveis de ambiente específicas do scraper  
- Componentes principais do pipeline sequencial e etapas de parsing  
- Utilitários de cache condicional, download HTTP, validação de host e robots  
- Suporte do pytest global do backend e alinhamento com marcações existentes

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
