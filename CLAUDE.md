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

### **Problema**
O `market_scraper` possui **duplicação e dispersão de responsabilidades** em relação à detecção e decisão sobre proteção anti-bot:

1. **Duplicação:** `AntiBotDetectionStep` (pipeline_steps.py) e `ResponseClassifier` (response_classifier.py) ambos testam padrões anti-bot independentemente.
2. **Bloqueio prematuro:** `AntiBotDetectionStep` retorna `StepResult.failure(message="anti_bot_page")` **mesmo após Playwright ter sucesso na aquisição**, impedindo parsing.
3. **Dispersão de decisão:** Decisão de escalonamento (HTTP → Playwright) está espalhada entre classificador, anti-bot detection e FetchHTMLStep, sem ponto único de controle.
4. **Impacto operacional:** URLs com sinais anti-bot (ex: script Cloudflare, reCAPTCHA) que Playwright consegue resolver retornam erro 429 mesmo com HTML válido.

### **Sintoma Observado**
- Requisição para URL protegida: curl_cffi recebe HTML com challenge
- ResponseClassifier classifica como `SCALE` → Playwright é acionado
- Playwright navega e obtém HTML com conteúdo de produto válido
- **Mas:** `AntiBotDetectionStep` detecta padrão legado do primeiro fetch → bloqueia com `failure`
- **Resultado:** `ParserResponse` com erro 429 em vez de 200 com payload

### **Objetivo da Correção**
Reestruturar o `market_scraper` para:
- **1 único DecisionGate:** Centralizar decisão de estratégia de aquisição (HTTP vs Browser)
- **Anti-bot como sinal, não barreira:** Detectar, classificar severidade, mas prosseguir com parsing se dados existirem
- **Limite de responsabilidade claro:** HTTPFetcher (curl_cffi) sinaliza apenas; BrowserFetcher (Playwright) executa; Parsers extraem; não se sobrepõem

### **Premissas**
1. `ResponseClassifier.classify()` e `detect_anti_bot_pattern()` já existem e funcionam
2. `PlaywrightPool` está operacional e acessível em startup
3. Redis está disponível para histórico de rate limiting
4. Testes existentes cobrem casos isolados; novos testes validarão fluxo de fallback

---

### Riscos, Impacto e Decisões

### **Decisão Técnica Principal**

| Decisão | Justificativa | Impacto |
|---------|---|---|
| **Criar `FetchDecisionGate`** | Centralizar decisão de tentativa (HTTP → Browser); evitar duplicação | Um ponto de verdade; lógica testável isoladamente |
| **Separar "detecção" de "bloqueio"** | Anti-bot é informação, não barreira absoluta | Permite parsing mesmo com sinais legados (ex: Playwright resolveu challenge) |
| **Remover `AntiBotDetectionStep` como etapa** | Lógica de anti-bot fica pré-parsing, no DecisionGate | Pipeline linear: FetchDecision → Fetch → Parse (sem etapa intermediária que bloqueia) |
| **Fallback automático em FetchHTMLStep** | Se curl_cffi classifica SCALE, tenta Playwright dentro da mesma etapa | Resposta final é sempre melhor tentativa disponível; simplifica pipeline |
| **Parser não decide anti-bot** | Parsing é extração pura; se há HTML, tenta extrair | Reduz responsabilidade; falha de parsing é falha de parsing, não anti-bot |

### **Risco Principal**

| Risco | Severidade | Probabilidade | Mitigação |
|-------|---|---|---|
| **Regressão:** Perder detecção anti-bot existente | Média | 🔴 Baixa | Manter `detect_anti_bot_pattern()` como função pura; testes unitários reutilizam padrões atuais |
| **Parser retorna lixo de challenge page** | Média | 🟡 Média | Validador de dados (`validator.py`) rejeita payloads vazios; logging de origem (curl_cffi vs Playwright) |
| **Playwright fica sobrecarregado (OOM)** | Alta | 🟠 Baixa | Pool com semáforo (max 5 contexts) + reciclagem a cada 50 req já existem; documentação obrigatória em Docker |
| **Timeout em Playwright bloqueia requisição** | Média | 🟡 Média | Timeout da etapa 15s + pipeline 20s; se Playwright timeout, retorna failure (não causa error 504) |
| **Mudança quebra teste existente** | Média | 🟡 Média | Refatorar testes em conjunto; fixtures reutilizadas |

### **Dependências**
- `shared.utils.url_validation` (já existe)
- `market_scraper.services.response_classifier.ResponseClassifier` (refatorado para ser pure)
- `market_scraper.services.playwright_pool.playwright_pool` (singleton já ativo)
- `market_scraper.utils.http_download.CurlffiHTTPClient` (continua igual)
- `structlog` (logging já consolidado)

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
