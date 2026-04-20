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

## Resumo e Estratégia do Plano

### Problema
O módulo `market_scraper` está conseguindo **navegar e acessar URLs de produto** em Mercado Livre, mas **não está extraindo dados úteis**; retorna 429 (anti-bot challenge) em praticamente todas das requisições a Mercado Livre, com taxa de sucesso **zero** para payload utilizável, enquanto Amazon e Magalu retornam dados mais "confiáveis".

### Sintoma Observado
- **Mercado Livre:** requisições retornam 429 `anti_bot_challenge` (challenge persistente em Camada 1 e Camada 3); HTML obtido (~34KB) contém padrão `suspicious-traffic-frontend`; sem sinais de produto; rate limiter ativa cooldown de 3600s após 3º fail, bloqueando novos testes
- **Amazon/Magalu:** requisições retornam 200 OK com payload útil (name + price) extraído, alguns casos de erros ou falsos positivos também foram identificados.
- **Logs:** eventos `fetch_gate_layer3_challenge_no_product_signals` indicam browser renderizando página de proteção, não página de produto

### Objetivo da Correção
Transformar `market_scraper` de um **serviço de navegação** para um **serviço de extração real**, desbloqueando coleta de dados de produtos em Mercado Livre através de:
1. **Sessão persistente** para reutilizar cookies/state entre requisições
2. **Bootstrap de domínio** antes de acessar URL de produto
3. **Parser de estado JavaScript** para extrair dados de JSON inline mesmo com DOM degradado
4. **Fingerprint unificada** para reduzir detecção anti-bot
5. **Rate limiter adaptativo** para não bloquear fase de recuperação

---

### Riscos, Dependências e Decisões

### Decisão Técnica Principal
**Sessão persistente de Playwright por domínio + parser de estado JavaScript** como caminho crítico para desbloqueio de Mercado Livre, substituindo abordagem stateless (novo contexto por requisição) por cache compartilhado com reutilização de cookies/localStorage.

| Aspecto | Detalhe |
|--------|--------|
| **Por que Sessão Persistente?** | Challenge anti-bot detecta contextos frescos; reutilizar cookie/session de navegação anterior reduz trigger de proteção |
| **Por que Parser JS?** | Mercado Livre renderiza JSON state (`__NEXT_DATA__`, scripts inline) que contém nome/preço/moeda mesmo quando DOM visual é degradado; extração de JSON é imune a bloqueios visuais |
| **Por que Bootstrap?** | Navegar primeiro para homepage/categoria do domínio aquece sessão + estabelece cookies antes de acessar URL específica do produto |
| **Por que Fingerprint Unificada?** | User-Agent pool (Firefox, Safari, Chrome) vs TLS fixo (Chrome124) cria inconsistência detectável; alinhamento reduz falso positivo de anti-bot |

### Risco Principal

| Risco | Severidade | Probabilidade | Mitigação |
|-------|-----------|--------------|-----------|
| **OOM Playwright (memory leak)** | 🔴 Alta | 🟡 Média | Reciclagem context a cada 50 req; flag `--disable-dev-shm-usage`; monitoramento RAM em tempo real |
| **Mudança contrato HTTP inadvertida** | 🔴 Alta | 🟠 Baixa | Usar feature flags; validação de `ParserResponse` schema; testes de contrato |
| **Fingerprint ainda detectada** | 🟡 Média | 🟡 Média | Fallback: rate limiter voltará a ativar cooldown; documentar e iterar em MVP+1 |
| **Rate limiter desligado = spam** | 🟡 Média | 🟠 Baixa | Usar flag temporal (`SCRAPER_RATE_LIMITER_BLOCK_ENABLED_UNTIL`) em produção; ligar automaticamente após fase de recuperação |
| **Timeout Playwright bloqueia pipeline** | 🟡 Média | 🟡 Média | Timeout global 30s; circuit breaker em requisição; rejeição com 429 (não 504) |
| **Parser JS quebra com mudança HTML Mercado Livre** | 🟠 Baixa | 🟠 Baixa | Parsers em cascata (JSON + DOM fallback); testes com HTML fixado (fixtures) |
| **Redis offline → perda de cache sessão** | 🟠 Baixa | 🟠 Baixa | Fallback em-memória (não persistente); logging + alert operacional |

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
