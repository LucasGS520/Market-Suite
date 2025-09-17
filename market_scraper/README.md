# Arquitetura de Scraping Leve
Este documento descreve o fluxo de coleta de dados do serviço `market_scraper` utilizando abordagens de baixo custo baseadas em **JSON**, **HTML estático** e pipeline sinérgico configurável.
O objetivo é extrair apenas os campos essenciais `name` e `current_price` de maneira discreta, com observabilidade, compliance e rollout controlado, evitando o uso de navegadores controlados pelo Playwright nesta fase do projeto.

## Visão Geral do Fluxo
1. A rota `/parse` recebe a URL do produto.
2. A função `scrape_product_common_async` normaliza o endereço, consulta o cache inteligente e aciona o pipeline ou orquestrador conforme feature flag e contexto.
3. O `MultiStrategyScraperOrchestrator` e/ou `SynergicPipeline` selecionam estratégias e etapas conforme configuração centralizada (`domain_policy.yaml`).
4. Cada tentativa é validada pelo `DataQualityValidator`; timeouts ou falhas acionam fallback para a próxima estratégia ou etapa.
5. Resultados válidos são armazenados no `IntelligentCacheManager` e retornados ao solicitante, respeitando TTL, ETag e políticas de domínio.
6. Métricas e logs estruturados são registrados para observabilidade e compliance.

## Políticas de Domínio e Configuração Centralizada
O módulo `domain_policy` mapeia cada marketplace para uma ordem de execução, contexto e modo de processamento:
- Estratégias leves (JSON) são priorizadas, seguidas por HTML estático e outras técnicas.
- O arquivo `domain_policy.yaml` centraliza estratégias, etapas de pipeline, modos de execução (`sequential`, `parallel`, `conditional`), limites de requisições e feature flags.
- Contextos (ex: `default`, `competitor`) permitem granularidade por tipo de página ou cenário.
- Novas estratégias, etapas ou domínios podem ser adicionados facilmente via YAML, sem alterar o core do código.

## Estratégias de Coleta e Pipeline
### JSON Endpoint
Classes derivadas de `JsonEndpointStrategy` executam chamadas HTTP a APIs públicas. Resultados válidos são cacheados para reutilização.

### HTML Estático
Estratégias herdadas de `HtmlStaticStrategy` priorizam Parsel (lxml), extraindo `JSON-LD` e meta-tags. BeautifulSoup é fallback para compatibilidade.

### SelectorLib
Para páginas instáveis, usamos **SelectorLib** com templates YAML em `selectorlib_templates`.

### Pipeline Sinérgico
O `SynergicPipeline` executa etapas configuráveis por domínio/contexto, compartilhando dados via `shared_context` e registrando métricas de latência, fallback e sucesso/falha.

## MechanicalSoup para Fluxos Simples
Utilizado para interações leves (login, filtros simples), combinando `requests` e `BeautifulSoup` sem overhead de navegador completo. Playwright é reservado para cenários avançados e não está ativo por padrão.

## Requests-HTML para Páginas Dinâmicas Leves
Utilizado para páginas que exigem renderização simples de JavaScript. Prefira Requests-HTML antes de recorrer ao Playwright. Limitações: depende de `pyppeteer`, não realiza navegação avançada, pode consumir mais recursos.

## Rollout, Feature Flags e Observabilidade
O rollout de funcionalidades críticas (ex: pipeline sinérgico) é controlado por feature flags no `domain_policy.yaml`, permitindo ativação gradual por domínio/contexto e rollback imediato.
- Métricas Prometheus (`SCRAPER_FEATURE_FLAG_TOTAL`, `SCRAPER_STRATEGY_TOTAL`, `SCRAPER_FALLBACK_TOTAL`, `SCRAPING_LATENCY_SECONDS`) monitoram decisões, latência e fallback.
- Logs estruturados registram decisões de rollout, execuções e bloqueios.
- O plano de rollout e rollback está documentado e testado, garantindo governança e rastreabilidade.

## Segurança, Compliance e Limites
- Respeito ao `robots.txt` antes de qualquer coleta.
- Limites de requisições por domínio configurados no YAML e aplicados via `RateLimiter` e `ThrottleManager`.
- Logs passam por sanitização (`sanitize_log_data`), evitando registro de dados sensíveis (cookies, tokens, credenciais).
- Coleta apenas dos campos essenciais, conforme LGPD/GDPR.

## Extensibilidade e Exemplos Práticos
Para adicionar novas estratégias, etapas ou domínios:
1. Implemente a classe derivando das bases existentes.
2. Registre no `domain_policy.yaml` em `strategies` ou `pipeline_steps`.
3. Defina a ordem e contexto em `policies` ou `pipeline_policies`.
4. Ajuste `strategy_execution` e `pipeline_execution` conforme necessidade.
5. Adicione testes unitários/integrados.
6. Monitore métricas após deploy para ajustes finos.

Exemplo de rollout:
```yaml
feature_flags:
  synergic_pipeline:
    mercadolivre.com.br:
      default:
        enabled: true
        rollout_percentage: 40
      competitor:
        enabled: false
```
Permite ativar o pipeline para 40% das requisições, com rollback imediato via YAML.

## Métricas e Monitoramento
Principais métricas Prometheus:
| Métrica | Descrição |
| ------- | --------- |
| `SCRAPER_STRATEGY_TOTAL` | Contador por etapa e status |
| `SCRAPER_FALLBACK_TOTAL` | Fallbacks acionados |
| `SCRAPING_LATENCY_SECONDS` | Latência por etapa |
| `SCRAPER_FEATURE_FLAG_TOTAL` | Decisões de rollout |
| `SCRAPER_HTTP_BLOCKED_TOTAL` | Bloqueios por rate limit ou robots.txt |
| `SCRAPER_URL_STATUS_TOTAL` | Status por domínio |

Dashboards Grafana e alertas Prometheus/Loki acompanham rollout, latência, taxa de sucesso e compliance.

## Resultado Esperado
Para cada URL, o serviço retorna um dicionário com `name` e `current_price`. Se o conteúdo não mudou, responde **304 Not Modified**. Bloqueios sucessivos podem suspender temporariamente o scraping.

## Checklist de Extensão e Compliance
- [x] Configuração centralizada no YAML
- [x] Código modular e extensível
- [x] Documentação e exemplos completos
- [x] Testes aprovados e cobertura validada
- [x] Observabilidade e compliance garantidos

## Referências Rápidas
- `AGENTS.md`: guia operacional para agentes e automações
- `market_scraper/services/domain_policy.yaml`: configuração centralizada
- `shared/metrics/metrics_scraper.py`: métricas e observabilidade
- `tests/unit/services/test_domain_policy.py`: exemplos de testes de seleção/contexto

### Configuração centralizada (`domain_policy.yaml`)
O arquivo ``services/domain_policy.yaml`` centraliza todas as decisões de orquestração do scraper;
Ele define:
- **`strategies`** - mapeia nomes amigáveis para classes de estratégia registradas no código.
- **`policies`** - ordena as estratégias por domínio e por contexto (ex.: `deault`, `competitor`) garantindo que as alternativas mais leves sejam executadas primeiro.
- **`pipeline_steps`** - cataloga as etapas do ``SynergicPipeline`` capazes de compartilhar contexto.
- **`pipeline_policies`** - descreve, por domínios e por contexto, a ordem das etapas executadas pelo pipeline.

```yaml
#Trechos ilustrativos do arquivo domain_policy.yaml
strategies:
   JSON_ML: MercadoLivreJsonStrategy
   HTML_ML: MercadoLivreStaticStrategy
   SELECTOR_GENERIC: SelectorLibStrategy

policies:
  mercadolivre.com.br:
    default:
      - JSON_ML
      - HTML_ML
    competitor:
      - HTML_ML

pipeline_steps:
  extruct: ExtructExtractionStep
  parsel: ParselExtractionStep
  requestshtml: RequestsHTMLRenderStep

pipeline_policies:
  mercadolivre.com.br:
    default:
      - extruct
      - parsel
      - requestshtml
    competitor:
      - requestshtml
      - parsel

strategy_execution:
  default:
    default: sequential
    competitor: sequential
  mercadolivre.com.br:
    default: conditional
    competitor: sequential
```

Cada contexto representa um cenário configurável (por exemplo, `product_type=competitor`).
Caso um contexto não seja encontrado para o domínio, o bloco `default` é utilizado automaticamente.
Isso permite priorizar estratégias mais leves para páginas monitoradas e reservar opções mais robustas apenas quando o usuário solicita comparações de concorrentes.

> Variáveis de ambiente permitem customizar a configuração sem alterar o código
> - ``DOMAIN_POLICY_FILE`` aponta para outro arquivo YAML.
> - ``DOMAIN_POLICY_HOT_RELOAD=1`` ativa recarga automática quando o arquivo é alterado

#### Fluxo operacional e fallback do pipeline
O ``SynergicPipeline`` garante que estratégias e etapas sigam uma ordem previsível, reutilizando intermediários e registrando métricas de latência e fallback.

```mermaid
flowchart LR
    A[Requisição /scrape/parse] ---> B{Cache válido?}
    B -- Sim --> C[Retorno imediato (304 ou cache hit)]
    B -- Não --> D[Carregar domain_policy.yaml]
    D --> E[Selecionar estratégias e etapas por domínio/contexto]
    E --> F[Executar SynergicPipeline]
    F --> G{Etapa bem-sucedida?}
    G -- Sim --> H[Validação e DataQuality]
    H --> I[Armazenar no IntelligentCacheManager]
    I --> J[Responder API]
    G -- Não --> K[Incrementar métricas de fallback]
    K --> F
```

Durante a execução:

1. O cache inteligente é consultado antes de iniciar etapas custosas.
2. A ordem de fallback é definida no ``domain_policy.yaml`` e percorre as alternativas até encontrar um resultado válido.
3. Cada etapa registra métricas estruturadas (tempo, status e fallback) para análise posterior no Prometheus.
4. O processamento pode ser **sequencial**, **paralelo** ou **condicional**, conforme o parâmetro ``execution_mode`` do ``SynergicPipeline``.

#### Contexto compartilhado, cache e métricas
As etapas compartilham informações pelo ``shared_context``. Isso reduz requisições redundantes (por exemplo, reaproveitando HTML pré-processado) e facilita instrumentação.

```mermaid
flowchart TD
    subgraph Pipeline
        S1[Etapa 1] -->|shared_context| S2[Etapa 2]
        S2 -->|shared_context| S3[Etapa 3]
    end 
    S1 -.->|Resultados intermediários| Cache[IntelligentCacheManager]
    Cache -->|TTL, ETag, Sig| S3
    Pipeline --> Metrics[[Prometheus / Logs estruturados]]
    Metrics --> Observabilidade[(Grafana / Alertmanager / Loki)]
```

- **Cache inteligente**: ``IntelligentCacheManager`` usa TTL, ETag e assinatura de conteúdo para evitar coletas redundantes.
- **Contexto compartilhado**: etapas podem inserir dados em ``shared_context`` (cookies, HTML bruto, headers) para as próximas etapas.
- **Métricas**: o módulo ``shared.metrics`` expõe contadores e histogramas específicos do pipeline.

| Métrica Prometheus | Descrição |
| ------------------ | --------- |
| ``SCRAPER_STRATEGY_TOTAL`` | Contador por etapa (classe) e status: ``success``, ``NOT_MODIFIED`` ou falha. |
| ``SCRAPER_FALLBACK_TOTAL`` | Contabiliza quantas vezes um fallback foi acionado entre etapas ou estratégias. |
| ``SCRAPING_LATENCY_SECONDS`` | Histograma de latência individual por etapa. |

Essas métricas complementam as métricas HTTP padrão e devem ser acompanhadas com alertas (ex.: aumento de ``fallback_total``) para reagir a bloqueios ou mudanças nos marketplaces.

#### Como adicionar novas estratégias ou etapas
1. **Criar a classe** em ``market_scraper/strategies`` (ou ``services/pipeline_steps``) herdando das bases existentes e garantindo validação com ``DataQualityValidator``.
2. **Registrar a classe** no ``domain_policy.yaml`` em ``strategies`` ou ``pipeline_steps``.
3. **Definir a ordem** em ``policies`` ou ``pipeline_policies`` para domínio e contexto desejado (ex.: `default`, `competitor`, `logged_user`).
4. **Ajustar os blocos `strategy_execution` e `pipeline_execution`** para indicar como cada contexto será executado (`sequential`, `parallel` ou `conditional`).
5. **Adicionar testes** cobrindo seleção e execução (``tests/unit/services/test_domain_policy.py`` e ``tests/integration/routes/test_strategy_selection.py`` contêm exemplos.)
6. **Monitorar métricas** após o deploy para ajustar TTL de cache, paralelismo ou limites.

#### Exemplo prático de extensão com nova biblioteca
Suponha que seja necessário utilizar uma biblioteca ``PlaywrightRenderStrategy`` apenas para páginas de concorrentes de um novo marketplace:

1. **Instale a dependência** e crie ``market_scraper/strategies/playwright_render.py`` implementando ``get_data`` com validação e uso de ``shared_context``.
2. **Registre a classe** em ``domain_policy.yaml`` dentro de ``strategies`` (ex.: ``PLAYWRIGHT_RENDER: PlaywrightRenderStrategy``).
3. **Atualize `policies`** para o domínio desejado definido o contexto ``competitor`` com a nova estratégia como último fallback. O contexto ``default`` pode continuar priorizando estratégias leves.
4. **Ajuste `strategy_execution`** para executar o contexto ``competitor`` em modo ``conditional`` (evitando que a etapa pesada rode quando o HTML já está disponível).
5. **Caso necessário**, inclua etapas adicionais em ``pipeline_steps`` / ``pipeline_policies`` para pré-carregar dados (por exemplo, uma etapa que capture cookies antes de chamar o Playwright).
6. **Crie Testes** unitários/integrados garantindo que o contexto ``competitor`` seleciona a nova estratégia e que o comportamento antigo permanece intacto para o contexto ``default``.

Esse fluxo garante que novas bibliotecas possam ser adicionadas de forma modular, habilitadas apenas quando configuradas via YAML e acompanhadas por métricas específicas.

#### Feature flags e rollout controlado
O arquivo ``domain_policy.yaml`` possui a seção ``feature_flags`` que controla funcionalidades sensíveis. Cada feature pode possuir valores por domínio e contexto, aceitando ``enabled`` (``true``/``false``) e ``rollout_percentage`` (0-100).
O valor final é determinado de forma determinística utilizando ``user_id`` e URL, permitindo liberar funcionalidades gradualmente sem inconsistências entre chamadas do mesmo usuário.

```yaml
feature_flags:
  synergic_pipeline:
    mercadolivre.com.br:
      default:
        enabled: true
        rollout_percentage: 40 #Ativa o pipeline para 40% das requisições
      competitor:
        enabled: false #mantém o comportamento anterior
```
* Valores ausentes herdam do bloco ``default``.
* ``rollout_percentage`` controla o canário: ``10`` significa que apenas 10% das requisições utilizarão a funcionalidade.
* Defina ``enabled: false`` (ou ``rollou_percentage: 0``) para realizar rollback imediato sem necessidade de deploy.

Ative ``DOMAIN_POLICY_HOT_RELOAD=1`` em desenvolvimento para testar novos percentuais sem reiniciar o serviço

#### Observabilidade do rollout
Três sinais principais acompanham a saúde do rollout:

1. **Métrica Prometheus ``scraper_feature_flag_total``**
  - Labels ``feature`` e ``state`` (`enabled`, `disabled`, `no_steps`).
  - Permite criar alertas (ex.: queda brusca na razão `enabled`/`disabled`).
2. **Logs estruturados**
  - `running_pipeline` inclui ``rollout`` e ``bucket_value`` indicando o percentual configurado e o valor sorteado para a requisição.
  - `pipeline_feature_disabled` e ``pipeline_skipped_no_steps`` sinalizam quando o pipeline não é executado por configuração.
3. **Métricas de latência e fallback**
  - ``SCRAPING_LATENCY_SECONDS`` e ``SCRAPER_FALLBACK_TOTAL`` ajudam a comparar o comportamento antes/depois do rollout.

Após alterações em ``feature_flags`` monitore:
- Grafana: dashboard do scraper (latência, taxa de sucesso, contadores ``scraper_feature_flag_total``).
- Loki: buscar eventos `pipeline_feature_disabled` para confirmar se o rollback foi aplicado.

#### Plano de rollout e rollback
1. **Preparação**
  - Ajuste o percentual inicial (ex.: 10%) no YAML e habilite hot reload em ambientes de teste.
  - Valide com testes automatizados (`pytest`) e smoke tests manuais.
2. **Rollout canário**
  - Publicar o YAML atualizado via pipeline de configuração.
  - Acompanhar ``scraper_feature_flag_total{state="enabled"}`` vs ``scraper_feature_flag_total{state="disabled"}``.
  - Observar histogramas de latência e logs de erro nos primeiros minutos.
3. **Escalonamento**
  - Se não houver regressões, aumentar gradualmente o ``rollout_parcentage`` (40% -> 70% -> 100%).
  - Documentar cada incremento no changelog interno.
4. **Rollback**
  - Em caso de falha, ajustar ``enabled: false`` ou ``rollout_percentage: 0`` e forçar recarga do YAML (hot reload ou restart leve).
  - Confirmar no Grafana que o contador `state="disabled"` voltou a subir e que não há novas execuções da feature.

Esses passos mantêm o serviço aderente às boas práticas de segurança (LGPD/GDPR), possibilitam auditoria das decisões e evitam instabilidade em produção.

#### Segurança, compliance e limites de scraping
- Respeitar ``robots.txt`` consultando ``utils/robots.txt`` antes de liberar novas rotas e durante tentativas de recuperação (`BlockRecoverymanager`, aborta quano o domínio proíbe o caminho).
- Utilizar ``ThrottleManager`` e ``RateLimiter`` para manter intervalos e janelas alinhados com os termos de uso; o contador `SCRAPER_HTTP_BLOCKED_TOTAL` é incrementado automaticamente quando o rate limit é atingido.
- Sanitizar logs com os utilitários de mascaramento de dados do diretório ``shared``; o serviço aplica `sanitize_log_data` para remover tokens, cookies e parâmetros sensíveis de URLs antes de registrar eventos.
- Configurar limites e comportamentos específicos por domínio no YAML, evitando que etapas pesadas sejam aplicadas indiscriminadamente. O bloco ``rate_limits`` define ``max_requests`` e ``window`` por host, refletidos em métricas no ``SCRAPER_URL_STATUS_TOTAL``.
- Seguir o princípio de minimização de dados (LGPD/GDPR), coletando apenas os campos essenciais (nome, preço, etc...).
- Documentar e revisar periodicamente exceções de compliance em conjunto com a equipe jurídica antes de ativar novas estratégias.


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

