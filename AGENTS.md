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

### Resumo e Estratégia do Plano

### **Objetivo**
Implementar a arquitetura em cascata de **aquisição de HTML com TLS impersonation nativo** (curl_cffi) substituindo `httpx` na `FetchHTMLStep`, complementada com fallback Playwright para cenários com JavaScript, eliminando bloqueios de fingerprint TLS e aumentando taxa de sucesso em Mercado Livre e marketplaces similares.

### **Resultado Esperado**
1. `FetchHTMLStep` usando `curl_cffi` com impersonation Chrome (drop-in replacement de download_html)
2. Classificador de resposta automatizando decisões de escalonamento entre camadas
3. Rate limiter adaptativo com histórico em Redis
4. Fallback Playwright com pool gerenciado
5. Contrato HTTP intacto; integração com `market_alert` funcional
6. Taxa de sucesso em Mercado Livre sem proxy externo
7. Testes de validação cobrindo Camadas 1 e 3

### **Estratégia de Execução**
- **Fases sequenciais**: Infraestrutura → Camada 1 (curl_cffi) → Camada 3 (Playwright) → Classificador → Testes
- **MVP focado**: Priorizar curl_cffi + Playwright; Camada 2 (proxy residencial) fica para fase pós-MVP
- **Integração incremental**: Cada camada validada isoladamente antes de integrar ao pipeline
- **Preservação de contrato**: Nenhuma mudança em `ParserRequest`/`ParserResponse` ou endpoints

### **Escopo**

#### **IN**
- Refatorar `utils/http_download.py` com curl_cffi
- Criar `services/response_classifier.py` para decisão automática de escalonamento
- Criar `services/playwright_pool.py` com pool de contexts
- Criar `infra/adaptive_rate_limiter.py` com histórico Redis
- Integrar classificador ao `routes/routes_scraper.py`
- Atualizar `FetchHTMLStep` para usar nova estratégia
- Testes de integração (Camada 1, Camada 3, decisões)
- Documentar mudanças em README.md

#### **OUT (Pós-MVP)**
- ❌ Camada 2 (proxy residencial) — apenas design, sem implementação
- ❌ Generalização para Amazon/Magalu (foco ML agora)
- ❌ Mudanças no contrato HTTP
- ❌ Otimizações de throughput beyond MVP
- ❌ Internacionalização de user agents (manter pt-BR)

### **Premissas**
1. Infraestrutura Redis existente está funcional e acessível (db 2 disponível)
2. Docker permite `--shm-size=2g` ou suporta `--disable-dev-shm-usage`
3. Python 3.10+ disponível
4. Curl com suporte SSL nativo (não WSL1 puro)
5. CI/CD existente suporta novo passo: `playwright install chromium`

---

### Riscos, Impacto e Decisões

### **Decisões Técnicas Principais**

| Decisão | Justificativa | Impacto |
|---------|---|---|
| **curl_cffi em Camada 1** | TLS JA3 impersonation nativo, 125ms, sem overhead | Drop-in para httpx, 80-90% casos resolvidos |
| **Playwright em Camada 3** | Headless Chromium, JA3 real Chrome, suporta JS renderization | 10-20% casos restantes, 5-10s por requisição |
| **Rate limiter com histórico Redis** | Adaptação por host/pattern, fallback automático | Reduz escalonamento desnecessário, melhora latência média |
| **Classificador independente** | Lógica de decisão centralizada, auditável | Facilita ajustes e testes; código não opaco |
| **Pool Playwright com Semaphore** | Limite de 5 contexts simultâneos | Proteção de OOM; throughput máximo 30req/min para fallback |
| **Sem Proxy em MVP** | Complexidade de gerenciamento de proxies | Focado em resolver TLS fingerprint (raiz); proxy fica para fase 2 |
| **Contrato HTTP inalterado** | Compatibilidade com consumers existentes (market_alert) | Zero breaking changes |

### **Riscos Principais**

| Risco | Severidade | Prob. | Mitigação |
|-------|---|---|---|
| **TLS fingerprint curl_cffi detectada futuro** | Alta | 🔴 Baixa (curl_cffi + Chrome impersonation são padrão) | Fallback sempre disponível em Camada 3 |
| **Memory leak Playwright (OOM)** | Alta | 🟡 Média | Reciclagem context a cada 50req; flag `--disable-dev-shm-usage` |
| **Mudança estrutura HTML Mercado Livre** | Média | 🟡 Média (historicamente rara) | Parser genérico + `__NEXT_DATA__` JSON (mais estável) |
| **Timeout Playwright bloqueia requisições** | Média | 🟡 Média | Timeout global 30s; circuit breaker em market_alert; rejeição com retry_after |
| **Rate limiter não converge** | Baixa | 🟡 Média | Tuning iterativo em MVP+1; thresholds iniciais conservadores |
| **Redis não responde em histórico** | Média | 🟠 Baixa | Fallback em-memória (não persistente) se Redis offline; logging de failure |
| **Docker `/dev/shm` insuficiente** | Alta | 🟠 Baixa (com doc) | Documentação obrigatória; CI testa com flag `--disable-dev-shm-usage` |

### **Dependências**

| Dependência | Versão | Instalação |
|---|---|---|
| **curl_cffi** | >=0.15.0 | `pip install curl_cffi` |
| **playwright** | >=1.40.0 | `pip install playwright` + `playwright install chromium` |
| **tenacity** | >=8.0 (já existe) | — |
| **httpx** | >=0.24 (já existe) | Mantém-se para fallback ou remoção futura |
| **Redis** | (já existe) | Sem upgrade necessário |
| **asyncio** | stdlib Python 3.10+ | — |
| **structlog** | (já existe) | — |

### **Impactos Arquiteturais**

- **Redução de acoplamento**: `download_html()` deixa de ser específica de httpx
- **Previsibilidade**: Taxa de sucesso sobe 75-80% (de 5-10% para 85-90%)
- **Observabilidade**: Novos logs estruturados (camada usada, classificação, histórico)
- **Capacidade**: Throughput Camada 1 cresce 3-5x (menos timeouts); Camada 3 limitada a 30req/min
- **Custo operacional**: RAM ~200MB adicionais por context Playwright; sem infra nova necessária
- **Latência p99**: Sobe de ~500ms para ~1s (Camada 1) + fallback Playwright (~10s) quando escala



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
