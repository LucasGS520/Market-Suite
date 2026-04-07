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

1. O código já avançou na direção certa:
`client_identity.py`, `bruteforce.py`, `services_auth.py`, `services_account.py`
2. Porém o runtime ainda mostra todos como `172.18.0.14`.
3. O ponto crítico de ambiente está em `docker-compose.hml.yml`: forwarded-allow-ips está em 172.28.0.0/16, mas os logs mostram tráfego vindo de 172.18.x.x.
4. Resultado: o servidor pode ignorar headers encaminhados pelo Nginx e continuar enxergando IP interno do proxy, gerando bloqueio cruzado.

---

## Análise de Riscos e Decisões Chave

- **Decisão arquitetural principal:** cada evento deve operar no menor escopo possível. O plano deve atacar 2 frentes ao mesmo tempo: isolamento lógico de chaves e consistência de execução em produção/HML.

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
