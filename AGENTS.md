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
Criar um ambiente de testes técnico, automatizado e alinhado ao papel do `market_orchestrator`, cobrindo o workflow Temporal, activities, contratos, configuração e pontos de integração com Redis, PostgreSQL e a camada consumidora em market_alert.

**Estratégia de Implementação**  
Montar a base de testes primeiro, depois cobrir o núcleo determinístico do workflow em unit, em seguida validar as activities e o worker em integration, e por fim fechar com testes técnicos, governança de execução e critérios de qualidade. O ponto de partida real é que o diretório de testes do módulo existe, mas ainda está vazio, e o bootstrap global de pytest em `pytest.ini` ainda está orientado para tests.

---

## Análise de Riscos e Decisões Chave

**Decisão Técnica Principal**  
separar claramente testes unitários de testes de integração, mantendo unit sem I/O real e integration com infraestrutura controlada, seguindo a estrutura proposta em `estrutura_ambiente_testes.md`.

**Risco Principal**  
flakiness por Temporal, Redis, SQL e dependências de processo no worker. Isso precisa ser mitigado com fixtures determinísticas, fakes/mocks para unit, isolamento por arquivo de teste e marcação explícita de suíte.

**Dependências**
- `config_orchestrator.py` para parametrização de ambiente.
- `worker.py` para bootstrap do worker e validação de infraestrutura.
- `workflow.py` para as regras determinísticas do fluxo.
- `dispatch_activity.py`, `status_activity.py`, `policy_activity.py` e `snapshot_activity.py` para validação dos caminhos de I/O.

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
