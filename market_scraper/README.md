# Arquitetura de Scraping Leve
Este documento descreve o fluxo de coleta de dados do serviço `market_scraper` utilizando abordagens de baixo custo baseadas em **JSON** e **HTML estático**.
O objetivo é extrair apenas os campos essenciais `name` e `current_price` de maneira discreta, evitando o uso de navegadores controlados pelo Playwright nesta fase do projeto.

## Visão Geral do Fluxo
1. A rota `/parse` recebe a URL do produto.
2. A função `scrape_product_common_async` normaliza o endereço para a versão mobile, consulta o cache e aciona o orquestrador.
3. O `MultiStrategyScraperOrchestrator` seleciona as estratégias definidas pela política de domínio e executa cada uma em sequência com limite de tempo configurável via `asyncio.wait_for`.
4. Após cada tentativa os dados são validados pelo `DataQualityValidator`; timeouts ou falhas acionam fallback para a próxima estratégia.
5. Quando o resultado é válido ele é armazenado no `IntelligentCacheManager` e retornado ao solicitante.

## Políticas de Domínio
O módulo `domain_policy` mapeia cada marketplace para uma ordem de execução:
- Primeiro são tentadas estratégias leves que consomem **endpoints JSON** públicos.
- Caso não retornem dados, o orquestrador realiza fallback para estratégias de **HTML estático**.

Essa política facilita a inclusão de novos marketplaces e novas técnicas de extração. Basta registrar a classe no `STRATEGY_REGISTRY` e definir a ordem em `DOMAIN_POLICES`.

## Estratégias de Coleta
### JSON Endpoint
As classes derivadas de `JsonEndpointStrategy` executam chamadas HTTP a APIs públicas quando disponíveis. No momento, mantemos stubs e priorizamos HTML estático para Mercado Livre, Amazon e Magalu. Resultados válidos podem ser armazenados em cache para reutilização.

### HTML Estático
As estratégias herdadas de `HtmlStaticStrategy` agora priorizam Parsel (lxml) para parsing de HTML:
- Extração de `JSON-LD` via XPath: `//script[@type="application/ld+json"]/text()`
- Meta-tags via CSS: `meta[property="og:title"]::attr(content)`

Quando essas fontes falham, aplicamos regras específicas por domínio (Mercado Livre, Amazon e Magalu). BeautifulSoup permanece como fallback usando backend `lxml` para compatibilidade.

### SelectorLib
Para páginas com layout instável, utilizamos a biblioteca **SelectorLib** com templates YAML verisonados em `selectorlib_templates`. A estratégia `SelectorLibStrategy` carrega o template correspondente ao domínio e extrai diretamente os campos `name` e `current_price`.

## Serviços Utilitários
- **IntelligentCacheManager** - armazena resultados de produtos por domínio e URL para reduzir requisições repetidas.
- **DataQualityValidator** - garante que `name` e `current_price` estejam presentes e que o preço seja válido.
- **IntelligentUserAgentManager** - rotaciona `User-Agent` para cada requisição, evitando bloqueios.
- **BlockRecoveryManager** e **HumanizedDelayManager** - auxiliam na recuperação de bloqueios, rotacionam recursos e, após uma suspensão temporária, tentam nova requisição ou consultam o cache para obter o HTML, registrando o resultado em log.

## Resultado Esperado
Para cada URL o serviço retorna um dicionário com `name` e `current_price`. Se o conteúdo não mudou desde a última coleta o endpoint responde **304 Not Modified**.
Bloqueios sucessivos podem resultar em suspensão temporária do scraping.

## Extensibilidade e Próximos Passos
Novas abordagens de coleta podem ser adicionadas ao sistema seguindo estas diretrizes:
1. **Registrar a estratégia** no `STRATEGY_REGISTRY` e definir sua ordem em `DOMAIN_POLICES`.
2. **Implementar a classe** derivando de `JsonEndpointStrategy` ou `HtmlStaticStrategy`, validando os dados com `DataQualityValidator`.
3. **Avaliar impactos** sobre cache, métricas de fallback e políticas de domínio. Estratégias mais pesadas (como uso de navegadores headless) devem ser adicionadas com cuidado para não afetar as atuais, preferindo mantê-las como último recurso.

Essas práticas mantêm o scraping leve e facilitam a evolução para outros métodos ou marketplaces.

