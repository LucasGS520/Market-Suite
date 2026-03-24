# Claude — Correção Camada de Inicialização

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

## Objetivo e Problemas a ser Resolvido

**Problema a Ser Resolvido:**  
Os logs mostram três falhas centrais na camada de inicialização e integração:
- O serviço da API falha por exaustão de tentativas de conexão com Temporal antes do Temporal atingir prontidão real.
- Há desalinhamento de readiness entre serviços: alguns workers validam Temporal enquanto a API ainda recebe timeout.
- Existe instabilidade de rede entre containers, com falhas intermitentes de resolução de hostname para db e redis.

**Objetivo do Plano:**  
Estabelecer uma inicialização determinística e resiliente para que:
1. A API só suba quando a dependência crítica estiver realmente pronta.  
2. Todos os serviços usem o mesmo critério de readiness para Temporal.  
3. A malha de containers fique estável (sem erro de DNS/hostname durante bootstrap).  

---

## Análise de Riscos e Decisões Chave

**Decisão Técnica Principal:**  
Adotar contrato único de prontidão para Temporal, com fail-fast controlado e janela de bootstrap compatível com o tempo real de subida do serviço.

**Risco Principal:**  
Aumentar robustez de startup pode elevar o tempo de inicialização total; mitigação via logs de progresso e health checks estritos e objetivos.

**Dependências Críticas:**  
Temporal, db, redis, rede Docker interna, ordem de dependências no compose e política de restart.

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
