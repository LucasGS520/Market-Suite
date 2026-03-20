# Claude — Correção Orquestrador Contínuo com Temporal

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

## Confirmação do Problema

### **Problema Principal (Crítico)**
**O Temporal Worker (orquestrador) conecta com sucesso, mas os clientes (API + Celery Workers) não conseguem atingir o servidor Temporal durante a inicialização, causando degradação do sistema para Celery-only e inativação da orquestração durável.**

**Raiz:** Race condition de inicialização — clientes tentam conectar ao Temporal **antes dele estar pronto** (42 segundos de diferença: 15:09:53 vs 15:10:50).

**Impacto:** 
- ❌ Workflows duráveis não são iniciados
- ❌ Signals de monitoramento não são entregues
- ✅ Sistema cai back para Celery (funciona parcialmente, mas sem plano de controle durável)

### **Problemas Secundários (Médio e Baixo Impacto)**

| # | Problema | Severidade | Impacto |
|---|----------|-----------|--------|
| 2 | Health check Temporal é bloqueante e sem retry | ⚠️ Média | Torna inicialização lenta; não aproveita retry exponencial |
| 3 | Clock drift de 18 segundos entre host e containers | ⚠️ Média | Falhas aleatórias na expiração de tokens/locks |
| 4 | Workers rodando como superuser/root | 🔴 Baixa (Dev) | Anti-pattern de segurança; aceitável em dev, deve ser corrigido em produção |

---

## Estratégia de Implementação

### **Objetivo Geral**
Garantir que **clientes Temporal (API + Workers) consigam conectar ao servidor durante a inicialização**, eliminando a race condition e permitindo que workflows sejam orquestrados no momento de startup.

### **Abordagem em 3 Camadas**

1. **Camada de Orquestração (Temporal):** Garantir que o servidor está PRONTO antes de aceitar clientes
2. **Camada de Cliente (API + Workers):** Implementar retry robusta e health check com backoff
3. **Camada de Infraestrutura (Docker Compose):** Adicionar health checks e dependency ordering

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
