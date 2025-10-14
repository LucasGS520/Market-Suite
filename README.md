# Market Suite
Market Suite (nome de desenvolvimento) é uma plataforma composta por serviços independentes para monitoramento de preços e envio
de alertas. A solução é dividida em três módulos principais:

- **market_alert** - API FastAPI responsável por gerenciar usuários, produtos monitorados, comparação de preços, regras de alertas e notificações. As tarefas assíncronas são executadas com **Celery**.
- **market_scraper** - microsserviço dedicado exclusivamente ao *web scraping*. Ele recebe uma URL e devolve as informações extraídas do anúncio.
- **shared** - componentes, utilitários e métricas compartilhadas entre os dois serviços.

A orquestração completa dos serviços é feita pelo arquivo ``docker-compose.yml``, que sobe banco de dados, Redis, API, workers e toda a stack de observabilidade de forma integrada.

## Visão Geral da Arquitetura
O diagrama abaixo apresenta como os serviços se comunicam e quais componentes externos são necessários para o funcionamento do sistema.
```mermaid
graph TD
    User[Usuário] --> API[market_alert]
    API --> |HTTP| Scraper[market_scraper]
    API --> |Tarefas| Worker[Celery Worker]
    Worker --> Beat[Celery Beat]
    API --> DB[(PostgreSQL)]
    Worker --> DB
    API --> Cache[(Redis)]
    Worker --> Cache
    API --> Prometheus
    Worker --> Prometheus
    Beat --> Prometheus
    Prometheus --> Grafana[(Grafana)]
    API --> Loki[(Loki + Promtail)]
    Worker --> Loki
```
* **Usuário → market_alert** - o usuário interage apenas com a API principal.
* **market_alert → market_scraper** - a API encaminha solicitações de coleta para o serviço de scraping.
* **Celery Worker** executa as tarefas assíncronas agendadas pela API, como scraping, comparação de preços e envio de notificações.
* **Celery Beat** agenda execuções periódicas para rechecagens de produtos e coleta de **métricas**.
* **PostgreSQL e Redis** armazenam dados persistentes e caches temporários.
* **Prometheus e Loki** coletam métricas e logs que podem ser visualizados no Grafana.

## Benefícios da Arquitetura
- **Separação de responsabilidades**: o serviço de scraping evolui independentemente da API principal, reduzindo acoplamento.
- **Escabilidade**: cada módulo pode ser escalado de forma isolada conforme a carga de trabalho
- **Reutilização**: recursos comuns ficam centralizados no diretório ``shared``, evitando código duplicado.
- **Observabilidade unificada**: métricas e logs são coletados de todos os serviços de maneira consistente. 

## Estrutura de Diretórios
```
market_alert/     # API principal e tarefas Celery
market_scraper/   # Serviço de scraping
shared/           # Utilidades e componentes em comum
```

## Serviço ``market_alert``
O `market_alert` centraliza a API e orquestra as tarefas assíncronas do sistema. Ele expõe endpoints REST, persiste dados no PostgreSQL e interage com o `market_scraper`
para coletar informações dos anúncios.

### Componentes principais
- **main.py** - inicializa a aplicação FastAPI, configura métricas e rate limiting e registra as rotas.
- **core/** - carrega variáveis de ambiente e define o ``Celery`` com filas e agendamentos.
- **routes/**, **schemas/** e **services/** - implementam os endpoints, validam dados e aplicam regras de monitoramento, comparação e alerta.
- **tasks/** - tarefas ``Celery`` para scraping, comparação de preços e envio de notificações.
- **notifications/** - gerencia o envio por e-mail, SMS, push, WhatsApp ou Slack.
- **models/** e **crud/** - mapeiam as tabelas e realizam operações no banco de dados.
- **utils/** e **templates/** - utilidades e modelos usados na geração das mensagens.

### Fluxo de monitoramento
1. A rota ``/monitored/scrape`` agenda a coleta de um produto no `Celery`.
2. A tarefa consulta o ``market_scraper``, atualiza o banco e dispara a comparação de preços.
3. Se alguma regra for atendida, uma nova tarefa envia as notificações pelos canais configurados.
4. Tarefas periódicas reexecutam verificações e expõem métricas em ``/metrics``.

### Resultados esperados de ``market_alert``
- Endpoints retornam confirmações de agendamento enquanto as tarefas populam o banco.
- Registros de comparação detalham preço médio, menor preço e discrepâncias.
- Métricas de API, filas e notificações ficam disponíveis para observabilidade.

## Serviço ``market_scraper``
O `market_scraper` é o serviço especializado em coletar dados de anúncios. Ele processa uma URL recebida, respeita regras de segurança (robots.txt e bloqueios de SSRF) e retorna um payload padronizado para os demais módulos.

Para detalhes operacionais consulte também [`market_scraper/README.md`](market_scraper/README.md).

### Pipeline mínimo de scraping
- Todas as requisições passam por um pipeline sequencial definido em `market_scraper/services/pipeline_steps.py`.
- A sequência padrão cumpre o requisito mínimo (`FetchHTML` → `JSON‑LD` → `HTML meta` → `fallback genérico`) e registra métricas de latência/sucesso por etapa.
- O `shared_context` do pipeline armazena URL normalizada, HTML, domínio de origem e o payload validado, permitindo que cada etapa opere de forma independente.
- A etapa `FetchHTMLStep` valida `robots.txt`, consulta cache local/Redis (quando configurado) e aplica limites de timeout com `httpx`.

### Componentes principais
- **main.py** – instancia a aplicação FastAPI e registra rotas de saúde, scraping e métricas.
- **routes/** – expõe ``/health/ping`` e ``/scraper/parse`` (alias ``/scrape/parse``) com o contrato `ParseRequest`/`ParserResponse` definido em ``shared/schemas/schemas_scraper.py``.
- **services/services_scraper_common.py** – cria o pipeline enxuto e aplica timeouts configuráveis antes de repassar o resultado à rota.
- **services/pipeline_steps.py** – define as etapas `FetchHTMLStep`, `JsonLdParserStep`, `HtmlMetadataParserStep` e `GenericFallbackParserStep`.
- **parsers/** – implementa transformações para JSON‑LD, metatags HTML e heurísticas genéricas.
- **utils/** – reúne utilitários compartilhados como validação de URL/SSRF, tratamento de preços, cache simples, respeito ao robots.txt e métricas.
- **tests/** – cobre unidade e integração do pipeline mínimo, incluindo cenários de URL inválida, ausência de preço e bloqueio por robots.
- **archive/** – mantém os arquivos `domain_policy.py` e `domain_policy.yaml` para referência histórica; eles não participam do pipeline atual.

### Configurações essenciais
- `market_scraper/core/config_scraper.py` concentra variáveis controladas por ambiente como `SCRAPER_STEP_TIMEOUT_SECONDS`, `SCRAPER_PIPELINE_TIMEOUT_SECONDS` e limites de requisições HTTP (`SCRAPER_HTTP_TIMEOUT_*`, `SCRAPER_HTTP_MAX_*`).
- O cache básico é habilitado via `SCRAPER_CACHE_ENABLED` e respeita o TTL `SCRAPER_CACHE_TTL_SECONDS`. O backend padrão (`SCRAPER_CACHE_BACKEND=memory`) utiliza um dicionário protegido por lock; o valor `redis` permanece reservado para futura expansão usando as credenciais compartilhadas (`REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD`).
- Todos os serviços reutilizam o `.env.common` para dados de infraestrutura. Configure `market_scraper/.env.market_scraper` quando precisar sobrescrever timeouts, TTLs ou o backend de cache.

### Papel na arquitetura
- Recebe requisições HTTP do ``market_alert`` ou de consumidores internos.
- Valida URL, marketplace suportado e disponibilidade pública antes de iniciar o download.
- Respeita robots.txt, aplica cache básico e expõe métricas (`SCRAPER_STEP_SUCCESS_TOTAL`, `SCRAPER_CACHE_LOOKUPS_TOTAL`, `SCRAPER_ROBOTS_CHECK_TOTAL`, entre outras) para acompanhamento no Prometheus.
- Em caso de falhas, retorna códigos conhecidos (`invalid_url`, `unsupported_marketplace`, `unsupported_by_robots`, `no_result`, `pipeline_timeout`).

## Módulo compartilhado ``shared``
O diretório ``shared`` concentra componentes reutilizáveis que dão suporte aos demais serviços.

### Organização
- ``__init__.py`` e ``exceptions.py`` - identificam o pacote e centralizam a exceção `ScraperError`.
- ``core/`` - configurações base e utilitários para leitura de variáveis de ambiente.
- ``enums/`` - enumerações de códigos de erro e resultados de bloqueios.
- ``infra/`` - infraestrutura comum localizada em ``shared/infra``: base ORM, scripts Redis e arquivos de observabilidade.
- ``metrics/`` - métricas Prometheus para HTTP, banco, cache, Celery e scraping.
- ``schemas/`` - modelos Pydantic que definem o contrato de dados entre os serviços, incluindo ``schemas_scraper.py`` com ``ScraperRequest`` e ``ScraperResponse``.
- ``utils/`` - funções auxiliares.
- ``tests/`` - testes que validam a integração e a consistência dos utilitários compartilhados.

### Papel na arquitetura
Os serviços ``market_alert`` e ``market_scraper`` importam esses recursos para compartilhar configurações, contratos de dados,
infraestrutura e métricas. Isso elimina duplicidade, padroniza o tratamento de erros e simplifica a manutenção da suíte.

## Como o sistema funciona
1. O usuário cria sua conta, autentica-se e obtém um token JWT para acessar a API
2. Com o token, cadastra URLs para monitoramento; a API agenda coletas e comparações no Celery.
3. O Celery Worker processa as tarefas, persiste dados no PostgresSQL e usa o Redis para estados rápidos.
4. O Celery Beat agenda rechecagens de produtos e coleta métricas de forma periódica.
5. Quando as regras de alerta são atendidas, o serviço de notificações envia mensagens pelos canais configurados.
6. Métricas e logs estruturados são expostos ao Prometheus e ao Loki para acompanhamento no Grafana.


## Primeiros Passos
### Requisitos
Antes de iniciar, garanta que os seguintes itens estão instalados:

* **Python 3.10+**
* **Docker e Docker Compose** (para execução completa do ambiente)
* **Redis** e **PostgreSQL** (caso opte por executar os serviços sem Docker)
* **Playwright** para coleta via navegador headless (Desativado nessa etapa do projeto)

1. Criar um ambiente virtual e instalar as dependências:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# fora do Docker
playwright install chromium
```

2. Configurar as variáveis de ambiente. O projeto utiliza três arquivos `.env`:
   - `./.env.common` - localizado na RAIZ do projeto
   - `market_alert/.env.market_alert`
   - `market_scraper/.env.market_scraper`

### Exemplo de ``.env.common``
```env
POSTGRES_USER=usuario
POSTGRES_PASSWORD=senha
POSTGRES_DB=banco_de_dados
DATABASE_URL=postgresql+psycopg2://usuario:senha@db:5432/banco_de_dados

REDIS_PASSWORD=senha

GF_SECURITY_ADMIN_USER=usuario_grafana
GF_SECURITY_ADMIN_PASSWORD=senha_para_grafana
GF_USERS_ALLOW_SIGN_UP=false
GF_PATHS_PROVISIONING=caminho_do_grafana

SLACK_WEBHOOK_URL=https://sua_url

SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=usuario
SMTP_PASSWORD=senha
SMTP_TLS=1
SMTP_FROM=alertas@example.com

TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxx
TWILIO_SMS_FROM=+5511999999999
TWILIO_WHATSAPP_FROM=+5511999999999

FCM_SERVER_KEY=AAAxxxxxxxxxxxxxxxxxxxx:APA91bG...

SECRET_KEY=sua_chave_secreta

LOCUST_HOST=http://host:0000
LOCUST_LOGIN_EMAIL=email_do_usuario@exemplo.com
LOCUST_LOGIN_PASSWORD=senha_do_usuario_exemplo

```
> **Nota:** ``LOCUST_LOGIN_EMAIL`` e ``LOCUST_LOGIN_PASSWORD`` devem permanecer a um usuário real.

### Exemplo de ``.env.market_alert``
```env
DATABASE_URL=postgresql+psycopg2://usuario:senha@db:5432/banco_de_dados

REDIS_PASSWORD=senha

SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=usuario
SMTP_PASSWORD=senha
SMTP_TLS=1
SMTP_FROM=alertas@example.com

TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxx
TWILIO_SMS_FROM=+5511999999999
TWILIO_WHATSAPP_FROM=+5511999999999

FCM_SERVER_KEY=AAAxxxxxxxxxxxxxxxxxxxx:APA91bG...

SECRET_KEY=sua_chave_secreta

ADAPTIVE_RECHECK_BASE_INTERVAL=7200

SLACK_WEBHOOK_URL=https://sua_url

SCRAPER_SERVICE_URL=http://url_serviço_de_scraping

```

### Exemplo de ``.env.market_scraper``
```env
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Cache básico por URL
SCRAPER_CACHE_ENABLED=1
SCRAPER_CACHE_BACKEND=memory
SCRAPER_CACHE_TTL_SECONDS=3600

SCRAPER_STEP_TIMEOUT_SECONDS=8.0
SCRAPER_PIPELINE_TIMEOUT_SECONDS=20.0

# Limites HTTP defensivos
SCRAPER_HTTP_MAX_REDIRECTS=3
SCRAPER_HTTP_MAX_CONTENT_LENGTH=2000000
SCRAPER_HTTP_MAX_CONNECTIONS=10
SCRAPER_HTTP_MAX_KEEPALIVE=5

SCRAPER_HTTP_TIMEOUT_CONNECT=3.0
SCRAPER_HTTP_TIMEOUT_READ=3.0
SCRAPER_HTTP_TIMEOUT_WRITE=3.0
SCRAPER_HTTP_TIMEOUT_POOL=3.0
SCRAPER_PRICE_TOLERANCE=0.0
```
## Recursos arquivados
- `market_scraper/archive/domain_policy.py` e `market_scraper/archive/domain_policy.yaml` armazenam a versão anterior baseada em políticas dinâmicas por domínio. Para reativá-los, mova os arquivos de volta para `market_scraper/services`, ajuste os imports do pipeline e reabilite o carregamento de políticas conforme indicado nos comentários internos.
- Demais utilitários legados permanecem preservados no diretório `market_scraper/archive/` e só devem ser restaurados caso o pipeline mínimo deixe de atender a um marketplace específico.

## Execução
Para levantar todo o ambiente com banco de dados, Redis e serviços auxiliares utilize:
```bash
docker-compose up --build
```

Os serviços também podem ser executados manualmente: 
```bash
# market_scraper
uvicorn market_scraper.main:app --port 8001

# worker e beat do market_alert
celery -A market_alert.core.celery_app:celery_app worker --loglevel=info
python market_alert/beat_with_metrics.py

# API
uvicorn market_alert.main:app --port 8000
```

## Comunicação entre serviços
O `market_alert` envia requisições HTTP ao `market_scraper` para processar páginas. Exemplo:
```http
POST http://market_scraper:8001/scraper/parse
Content-Type: application/json

{
  "url": "https://exemplo.com/produto",
  "product_type": "monitored",
  "user_id": "<UUID>"
}
```

```json
{
  "name": "Produto Exemplo",
  "current_price": 99.90,
  "old_price": 120.0,
  "thumbnail": "https://img.exemplo.com/123.jpg",
  "free_shipping": true,
  "seller": "Loja X",
  "shipping": "Frete Grátis"
}
```

## Observabilidade
- Métricas expostas em `/metrics` (API, worker e beat) e coletadas pelo **Prometheus**.
- Logs enviados ao **Loki/Promtail**.
- Painéis de visualização no **Grafana** e alertas via **AlertManager**.
- Auditoria de scraping disponível em `/audit`.

### Metas 
- **Latência de scraping (P95)** ≤ 5 s.
- **Taxa de erros de scraping** ≤ 1 %.

## Testes
Execute a suíte de testes:
```bash
pytest
```

Exemplos de execução por módulo:

```bash
pytest market_alert     # Testes da API
pytest market_scraper   # Testes do scraper
pytest shared           # Testes dos componentes compartilhados
```

## Licença
Distribuído sob a [MIT License](LICENSE). (APENAS EXEMPLO)
