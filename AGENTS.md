# AGENTS.md — Guia para Agentes de IA (MarketSuite)

Este arquivo é um guia específico para agentes de IA que interagem com o código do projeto MarketSuite. Ele complementa os `README.md` voltado a pessoas desenvolvedoras, oferecendo contexto operacional do repositório, listagem de serviços e tarefas, utilidades internas e boas práticas para automação e manutenção.

> Nota: Sempre que novos módulos, tarefas ou serviços forem introduzidos, este arquivo deve ser atualizado. O AGENTS.md é um documento vivo e deve refletir a realidade do projeto.

## Objetivo
- Descrever como agentes de IA devem navegar no repositório e usar os serviços disponíveis, com foco na integração `market_alert` ⇄ `market_scraper`.
- Fornecer atalhos para localizar documentação e código relevantes de cada serviço.
- Explicar rotinas essenciais (execução local, docker-compose, testes, migrações e observabilidade).
- Centralizar convenções internas necessárias para manter integridade entre `market_alert`, `market_scraper` e os módulos compartilhados em `shared/`.
- Indicar procedimentos de validação antes de concluir alterações.

---

## Referências
- `README.md`: visão geral da suíte, topologias de execução e checklist rápido para pessoas desenvolvedoras
- `market_alert/README.md`: responsabilidades, fluxos e comandos do orquestrador.
- `market_scraper/README.md`: detalhes e estratégias do microserviço de scraping.

## Como Usar Este Documento
- Utilize este arquivo omo manual operacional para automações, integrações entre serviços e inspeção de métricas
- Para visão conceitual, requisitos funcionais e setup humano consulte o `README.md` e, quando precisar de detalhes específicos, abra a documentação do serviço correspondente.

## Sumário Rápido
- Visão Geral da Arquitetura e Serviços: resumo de serviços, responsabilidades e como iniciar.
- Infra e Observabilidade: portas, métricas, Prometheus/Grafana/Loki.
- Diretrizes de Desenvolvimento para Agentes: tipagem, docstrings, testes, métricas.
- Tarefas e Comandos de Execução: pré-requisitos, `.env`, Docker e execução manual.
- Tarefas Celery disponíveis: assinaturas e efeitos das tasks.
- Exemplos de chamadas de API: autenticação, scraping, comparação.
- Como Manter o AGENTS.md Atualizado: rotina de revisão do documento.
- Checklist de Cobertura Essencial: verificação rápida antes de releases.

## Diretrizes de Desenvolvimento para Agentes

- Linguagem e comentários: mantenha docstrings e comentários em português, descrevendo propósito, parâmetros, retornos e exceções. Evite comentários redundantes; foque em contexto e decisões. Siga esse padrão para comentários e Docstrings: (Ex: #Comentário Padrão vem seguido da Hastag, """ Docstrings possui espaço após incio e fim """).
- Tipagem: use type hints em todas as funções públicas; mantenha assinaturas estáveis ou com parâmetros opcionais para compatibilidade.
- Estrutura e estilo: siga o padrão existente do repositório; não introduza linters/formatadores novos sem alinhamento. Não use `print`; logue com `structlog` e incremente métricas quando aplicável.
- Testes: escreva/ajuste testes com `pytest`; prefira casos pequenos e parametrizados próximos do código alterado. Execute `pytest -q` antes de propor mudanças.
- Métricas: ao criar fluxos relevantes, exponha contadores/histogramas no pacote `shared/metrics/*` e reutilize nomes/padrões já existentes. Atualize `/metrics` quando necessário.
- Pesquisa no código: prefira `rg` (ripgrep) para buscas rápidas; se indisponível, use `grep -Rni` com exclusões de diretórios (`.venv`, `.git`, caches). Exemplos: `rg -n "metrics|/metrics"`, `rg -n "collect_.*_task" market_alert`.
- Commits: mantenha mensagens claras no formato do tipo de mudança (ex.: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`), sempre traga a frase utilizada para o commit ao final da resposta (Ex: feat: Add nova instrução ao AGENTS.md). Faça mudanças pequenas e coesas; referência arquivos/rotas afetadas. Evite criar branches sem necessidade ou renomear arquivos amplamente.
- Pull requests: prefira PRs curtos e focados com descrição objetiva do impacto (API, tasks, métricas, migrações). Inclua checklist de testes e validações manuais quando aplicável.
- Alteração de interfaces: tenha extrema cautela ao mudar contratos de API, esquemas Pydantic, assinaturas de tasks Celery e estruturas de resposta do scraper. Preserve retrocompatibilidade (parâmetros opcionais com default), documente deprecações e atualize `AGENTS.md`, `README.md` e testes.
- Banco e migrações: não modifique esquemas sem migrar via Alembic; descreva riscos e plano de rollback. Nunca apague dados em massa em rotinas automatizadas.
- Observabilidade: ao introduzir funcionalidades, inclua métricas relevantes (latência, contadores de erro, tamanhos de fila) e logs estruturados. Atualize `shared/infra/prometheus/alert_rules.yml` se o SLO for afetado.
- Segurança e segredos: nunca logue tokens/senhas; use `.env` e utilidades em `shared/infra` para acessar segredos. Evite hardcode de URLs/credenciais.
- Compatibilidade local/Docker: mantenha portas alinhadas ao `docker-compose.yml`; evite conflitos (ex.: métricas Beat 8001, Worker 8002, API 8000, Scraper 8010 em dev).
- Ao final de cada Sprint, Etapas ou Fases, trazer alertas para que haja atualização nos arquivos `README.md` e `AGENTS.md`.

### Fluxo Alto Nível
1) Usuário → `market_alert` (API) para criar monitoramentos/solicitar coletas.
2) `market_alert` agenda tarefas → Celery Worker (Redis como broker).
3) `scraper_client` consulta `market_scraper` quando necessário e persiste/atualiza dados.
4) Regras disparam notificações; observabilidade registra métricas/logs.
5) Celery Beat agenda rechecagens e rotinas de manutenção.

## Tarefas e Comandos de Execução

### Arquivos de ambiente (.env)
- O projeto utiliza três arquivos de configuração:
  - `./.env.common` (raiz)
  - `market_alert/.env.market_alert`
  - `market_scraper/.env.market_scraper`
- Carregamento: `shared/core/config_base.py` carrega `./.env.common` e, por serviço, o arquivo `.env.<serviço>`. Em Docker, a variável `ENV_FILE` já aponta para o arquivo correto de cada serviço.
- Boas práticas: não commitar segredos; use valores dummy em exemplos; evite imprimir variáveis sensíveis em logs.

### Exemplos de chamadas de API
- Autenticação (obter token JWT):
  - `POST /auth` (form-urlencoded)
  - Exemplo `curl`:
    - `curl -X POST http://localhost:8000/auth -H "Content-Type: application/x-www-form-urlencoded" -d "username=email@exemplo.com&password=SuaSenha"`
  - Resposta: `{ "access_token": "...", "token_type": "bearer" }`

- Agendar scraping de produto monitorado:
  - `POST /monitored/scrape`
  - Headers: `Authorization: Bearer <token>`; `Content-Type: application/json`
  - Body (JSON): `{ "name_identification": "Notebook XYZ", "product_url": "https://www.mercadolivre.com.br/MLB-...", "target_price": 3500.00 }`
  - Efeito: agenda `collect_product_task`; retorna 202 com mensagem de agendamento.

- Agendar scraping de concorrente:
  - `POST /competitors/scrape`
  - Headers: `Authorization: Bearer <token>`; `Content-Type: application/json`
  - Body (JSON): `{ "monitored_product_id": "<UUID-do-monitorado>", "product_url": "https://www.mercadolivre.com.br/MLB-..." }`
  - Efeito: agenda `collect_competitor_task`; retorna 202.

- Listar produtos monitorados e concorrentes:
  - `GET /monitored` → lista monitorados do usuário.
  - `GET /competitors/{monitored_product_id}` → lista concorrentes do monitorado.

- Rodar comparação manualmente:
  - `POST /comparisons/{monitored_id}/run?tolerance=0.01&price_change_threshold=0.02`
  - Headers: `Authorization: Bearer <token>`
  - Resposta: objeto de comparação com agregados; pode disparar notificações dependendo das regras.

- Chamada direta ao serviço de scraping (opcional, para testes):
  - `POST http://localhost:8001/parse`
  - Body (JSON): `{ "url": "https://www.mercadolivre.com.br/MLB-...", "product_type": "monitored" }`
  - Resposta: `{ "name": "...", "current_price": 1234.56, "marketplace": "..." }` ou `304 Not Modified`.

## Como Manter o AGENTS.md Atualizado

### O que fazer
- Revisar este documento a cada sprint ou nova versão, e sempre que houver mudanças relevantes de arquitetura/fluxos.
- Registrar imediatamente novos serviços, rotas de API, tarefas Celery, utilitários compartilhados, métricas/portas e variáveis de ambiente (incluindo como iniciar, dependências e integrações).
- Comparar o conteúdo com o `README.md` para evitar redundâncias: mantenha aqui instruções operacionais para agentes; no `README.md`, mantenha setup humano e visão geral.

> Nota: Um guia desatualizado prejudica a confiabilidade do agente e pode levar a ações incorretas (ex.: chamar endpoints removidos, agendar tarefas com parâmetros inválidos ou ignorar limites/portas atualizadas).
