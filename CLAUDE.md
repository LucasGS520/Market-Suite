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

## **Diagnóstico Scraper Atual**

O `market_scraper` está estruturado como serviço de scraping por pipeline, com arquitetura em camadas (transporte, orquestração, coleta, extração, pós-processamento, infraestrutura), contratos tipados entre etapas, suporte operacional para cache/robots/rate limiting/telemetria.

**Problema:** O serviço `market_scraper` está operacional como infraestrutura de API, mas falha de forma dominante na extração de produtos reais sob proteção anti-bot. A taxa de erro é dominada por timeouts do browser (75% das falhas), detecção de padrões anti-bot sem fallback efetivo, e divergência de configuração entre ambientes. O serviço não possui identidade operacional persistente (proxy rotation, SessionPool, gerenciamento de cookies por sessão, aposentadoria de sessão ruim).

**Sintoma observado:**
- Staging: 75% `browser_timeout` (após ~75s), `anti_bot_pattern_detected` sem retry com nova identidade, `extraction_chain_exhausted` por HTML de challenge sem sinais de produto
- Falhas mapeadas como: `504` (timeout) ou `422` (extraction_empty)
- Mesma URL sucede em dev (budget 75s) mas falha em staging/production (budget divergente)
- Logs mostram `classification_reason` inconsistente quando browser está envolvido
- HTTP primary funciona, mas entrega challenge HTML que browser não consegue resolver

**Objetivo da correção:**
- Tornar coleta resiliente sob proteção real via proxy rotation, SessionPool, aposentadoria de sessão
- Normalizar configuração entre ambientes e remover divergências (code default vs. .env vs. README)
- Reduzir timeouts do browser ajustando navegação e concorrência
- Melhorar telemetria para rastreabilidade clara de cada failure point
- Retornar degradação controlada (200 com telemetria) quando houver dados confiáveis, em vez de 422/504

**Premissas:**
- Crawlee ProxyConfiguration e SessionPool estão disponíveis na versão instalada
- Proxy list ou proxy service está configurável via env (será definido em config)
- HTTP primary com curl_cffi já funciona para não-challenge URLs (não será revertido)
- Parser (extruct → parsel → beautifulsoup) funciona quando HTML é válido (validado por testes)
- Staging é ambiente controlado onde concorrência pode ser reduzida para debug
- Produção exigirá monitoramento antes de escalar concorrência

---

## Riscos, Impacto e Decisões

**Decisão Técnica Principal:**
Migrar de coleta "browser-only fallback quando falha HTTP" para coleta com **identidade operacional explícita**: proxy rotation per-session, SessionPool com session retirement em anti_bot/timeout/403/429, cookies persistentes por sessão, fingerprint agressivo, navegação ajustada, e telemetria rastreável em cada estado de transição.

**Risco Principal:**
- **Risco Alto**: Introduzir `ProxyConfiguration` e `SessionPool` altera o comportamento do browser/HTTP collectors; pode mascarar ou expor regressões em URLs não-challenge; exige testes extensivos antes de produção
- **Risco Médio**: Mudar contrato de resposta (aceitar degradação como 200 em vez de 422) pode quebrar consumidores que esperam 422 em erro
- **Risco Médio**: Reduzir concorrência do browser de N para 1 reduz throughput imediato mas melhora previsibilidade para debug

**Impacto Atual:**
- **Negócio**: Zero produtos extraídos em staging sob challenge; impossível escalar para produção sem remediation
- **Operação**: Timeouts recorrentes esgotam orçamento, causam 504 ou 422; logging insuficiente para diagnosticar se é proxy, timeout, ou bug assíncrono
- **Engenharia**: Testes passam mas não cobrem anti-bot real; divergência de configuração cria inconsistência entre ambientes

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
