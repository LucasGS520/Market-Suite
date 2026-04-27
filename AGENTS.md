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

### **Objetivo**
Transformar o módulo `market_scraper` de uma arquitetura complexa e dispersa (com coexistência de fluxos legado/novo, responsabilidades sobrepostas e múltiplos caminhos de decisão) para uma arquitetura simples, modular e determinística, totalmente alinhada aos documentos `estrutura_redefinicao_ideal_scraper.md`, `requisitos_ideais_scraper.md` e `arquitetura_alvo_scraper.md`.

### **Resultado Esperado**
1. Módulo reorganizado em 6 camadas explícitas com responsabilidades rígidas e sem sobreposição
2. Fluxo canônico único: validação → coleta finalizada → extração em cadeia fixa → pós-processamento → resposta HTTP
3. Remoção de caminhos legados complexos, wrappers redundantes e decisões dispersas
4. Ferramentas obrigatórias (Crawlee, curl_cffi, Playwright, Extruct, Parsel, BS4+lxml) integradas coesivamente
5. DTOs fechados e tipados substituindo dicionários abertos compartilhados
6. Telemetria obrigatória consolidada e rastreável
7. Compatibilidade total com contrato externo mantida
8. Taxa de sucesso mantida ou melhorada; latência reduzida por eliminar overhead arquitetural

### **Estratégia de Execução**
- **Análise e Preparação** — validar mapeamento, definir dependências, preparar ambiente de teste
- **Refatoração e Limpeza** — remover redundâncias, consolidar código disperso, eliminar coexistência novo/legado
- **Reorganização Estrutural** — criar nova hierarquia de diretórios conforme arquitetura alvo
- **Implementação de Coleta** — integrar Crawlee como framework para crawlers, curl_cffi + Playwright como executores
- **Implementação de Extração** — cadeia determinística com Extruct → Parsel → BS4+lxml
- **Implementação de Pós-processamento** — normalização, validação e preparação de resposta
- **Integração de Orquestração** — unificar todas as camadas com use case canônico
- **Integração HTTP/Contrato** — ajustar rota para ser casca fina e delegar ao use case
- **Infraestrutura e Observabilidade** — consolidar cache, limites, pool, telemetria
- **Testes e Validação** — suite completa cobrindo unitário, integração e regressão
- **Remoção de Legado** — eliminar código antigo após paridade confirmada
- **Documentação e Hardening** — finalizar documentação e ajustes finais

---

## Riscos, Dependências e Decisões

### **Decisões Técnicas Principais**

| Decisão | Justificativa | Impacto |
|---------|---|---|
| **Crawlee como framework para crawlers** | Oferece AdaptivePlaywrightCrawler, integra curl_cffi, Playwright e stealth nativo; elimina necessidade de múltiplos wrappers | Novas dependências; potencial breaking se Crawlee tiver limitações não previstas |
| **Cadeia extração fixa (Extruct → Parsel → BS4)** | Ordem determinística melhora previsibilidade e facilita depuração; termina na primeira válida | Pode perder cenários onde segunda estratégia seria melhor; mitigado por ordem bem pensada |
| **DTOs fechados em vez de dicionários abertos** | Type safety, documentação implícita, facilita testes; elimina surpresas de campos arbitrários | Maior verbosidade inicial; trade-off aceitável por ganho em previsibilidade |
| **HTTP sempre precede browser, sem coexistência** | Reduz complexidade, eleva performance média; browser é fallback, não padrão | Casos raros onde browser seria melhor desde início; mitigado por política clara de escalonamento |
| **Remoção total de legado após validação** | Clareza arquitetural e facilita manutenção futura | Requer validação rigorosa antes; impossível voltar a comportamento antigo sem refatoração |
| **Telemetria estruturada obrigatória com trace_id** | Rastreabilidade de cada decisão; facilita auditoria de falhas | Overhead mínimo; trade-off aceitável |

### **Dependências**

1. **Crawlee**
O Crawlee para Python expõe `BeautifulSoupCrawler`, `ParselCrawler` e `PlaywrightCrawler`, e também oferece `AdaptivePlaywrightCrawler` para alternar entre HTTP e browser quando isso trouxer ganho operacional. Isso encaixa bem com a estratégia “HTTP primeiro, browser quando necessário”, sem transformar browser em caminho padrão.
- Deve estar na camada de descoberta (crawler)
- Usada como framework principal para spiders escaláveis

2. **curl_cffi**
Cliente HTTP python, imita fingerprints de browsers reais para evitar detecção
- Deve estar na camada de requisição/anti-detecção, camada mais leve de requisição e tratamento anti-bot

3. **Playwright**
Automatizador de browsers para conteudo dinâmico
- Camada de Requisição, camada mais pesada quando necessário para tramento de anti-bloqueio

4. **Extruct**
Extrai metadados embutidos (JSON-LD, Microdata, Open Graph, RDFa) de HTML
- Camada de Extração/Parsing
- Aplicada pós-download para dados estruturados

5. **Parsel**
Biblioteca de seletores CSS/XPath otmizada, leve e rápida
- Camada de Extração/Parsing
- Integrar para queries precisas

6. **Beautifulsoup**
Parser tolerante de HTML/XML para navegação e extração simples
- Camada de extração/Parsing
- Integrado com **lxml**, para otmizar performance em grandes volumes

### **Impactos Arquiteturais**

- **Redução de acoplamento:** Eliminação de dependências cíclicas entre routes, pipeline e utils; DTOs explícitos como fronteiras
- **Melhoria de previsibilidade:** Fluxo linear determinístico vs múltiplos caminhos; decisões centralizadas no orquestrador
- **Aumento de observabilidade:** Telemetria obrigatória em cada etapa; trace_id propagado; logs estruturados
- **Redução de throughput overhead:** Eliminação de wrappers redundantes e decisões tardias dentro do parsing
- **Melhoria de manutenibilidade:** Nomenclatura clara, organização coerente, responsabilidades rígidas
- **Potencial impacto de latência:** p50/p95 deve cair (menos overhead); p99 pode flutuar (dependendo de falha rate)
- **Impacto operacional:** Curva de aprendizado inicial para nova arquitetura; após estabilizar, manutenção simplificada

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
