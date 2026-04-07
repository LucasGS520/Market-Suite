# Claude — Preparação e Alinhamento de Configurações

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

## Objetivo e Problemas Identificados

**Resumo**

- **Problema a resolver:** o sistema está usando o IP visto pelo container, não o IP real do usuário, então vários usuários caem na mesma chave Redis e acabam bloqueados em conjunto. O ponto crítico está em `bruteforce.py`, consumidos por `services_auth.py` e `routes_login.py`.

- **Objetivo do plano:** separar corretamente a identidade de cada cliente, impedir bloqueio cruzado entre usuários e padronizar as chaves Redis para que cada entidade tenha sua própria governança.

---

## Análise de Riscos e Decisões Chave

- **Decisão técnica principal:** parar de depender de `request.client.host` como identidade única e passar a resolver a identidade por uma camada central, confiando em headers de proxy apenas quando o tráfego vier de um proxy confiável.

- **Risco principal:** corrigir só o proxy sem mudar as chaves Redis continua causando bloqueio coletivo; corrigir só a chave sem corrigir a origem do IP gera identidade errada e métricas falsas.

- **Dependências:** Nginx/HML em `nginx.hml.conf`, startup da API em `docker-compose.hml.yml`, Redis operacional, e testes integrados com múltiplos usuários atrás do mesmo proxy.

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
