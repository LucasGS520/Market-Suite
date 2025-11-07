# AGENTS.md — Guia para Agentes de IA (Market Suite)

Este arquivo é um guia específico com instruções operacionais para agentes de IA que interagem com o código do projeto MarketSuite.
 Ele complementa os `README.md` voltado a pessoas desenvolvedoras, oferecendo contexto operacional do repositório, listagem de serviços e tarefas, utilidades internas e boas práticas destacando convenções internas, fluxos críticos, comandos frequentes e gatilhos de manutenção contínua.

> Nota: Sempre sincronize o conteúdo deste arquivo com o `README.md` e com os READMEs específicos dos serviços. Registre mudanças de arquitetura, novas filas, métricas ou variáveis assim que forem introduzidas.

## Objetivo
- Descrever como agentes de IA devem navegar no repositório e usar os serviços disponíveis.
- - Mapear os módulos ativos (`backend/` e `frontend/`) e apontar onde estão as responsabilidades de API, tarefas assíncronas, scraping e interface web.
- Fornecer atalhos para localizar documentação e código relevantes de cada serviço.
- Explicar rotinas essenciais (execução local, docker-compose, testes, migrações e observabilidade).
- Consolidar diretrizes de código, observabilidade, segurança e qualidade para que automações mantenham integridade entre serviços.

---

## Referências
## Referências imediatas
- `README.md`: visão geral da suíte, arquitetura e fluxos ponta a ponta.
- `backend/market_alert/README.md`: detalhes da API FastAPI, workers Celery e contratos de monitoramento.
- `backend/market_scraper/README.md`: responsabilidades do microserviço de scraping, pipeline de parsing e boas práticas.
- `frontend/README.md` (quando presente): convenções da aplicação React + Vite e instruções de build/deploy.

## Como Usar Este Documento
- Utilize este arquivo como manual operacional para automações, integrações entre serviços.
- Para visão conceitual, requisitos funcionais e setup humano consulte o `README.md` e, quando precisar de detalhes específicos, abra a documentação dos serviços correspondentes.

## Visão arquitetural rápida
- **Frontend (`frontend/`)**: aplicação React 18 servida por Vite, com servidor Express para produção. Consome a API pública e oferece dashboards responsivos.
- **Backend (`backend/`)**: agrega `market_alert` (API FastAPI, Celery Worker e Beat) e `market_scraper` (FastAPI dedicada a scraping). Recursos compartilhados ficam em `backend/shared/` (config, métricas, contratos Pydantic, clientes externos).
- **Infraestrutura de apoio**: PostgreSQL, Redis, Prometheus, Grafana, Loki e Alertmanager são orquestrados via `docker-compose.yml`.
- **Fluxo alto nível**: usuários interagem com o frontend → frontend chama a API `market_alert` → API agenda tarefas Celery → worker conversa com o `market_scraper`, Redis e PostgreSQL → observabilidade coleta métricas/logs → notificações são disparadas conforme regras.


## Diretrizes de Desenvolvimento para Agentes
- **Linguagem, Docstrings e comentários**: mantenha docstrings e comentários em português, descrevendo propósito, parâmetros, retornos e exceções. Evite comentários redundantes; foque em contexto e decisões. Siga esse padrão para comentários e Docstrings: (Ex: #Comentário Padrão vem seguido da Hastag, """ Docstrings possui espaço após incio e fim """).
- **Tipagem**: mantenha type hints em funções públicas e preserve compatibilidade adicionando parâmetros opcionais quando necessário.
- **Estrutura e estilo**: siga o padrão existente do repositório; não introduza linters/formatadores novos sem alinhamento. Evite `print`; utilize `structlog` e incremente métricas quando essencial e possível.
- **Testes**: crie ou ajuste testes com `pytest`. Execute `pytest -q` nos módulos afetados antes de concluir alterações.
- **Métricas**: ao criar fluxos relevantes, exponha contadores/histogramas e reutilize nomes/padrões já existentes.
- **Pesquisa no código**: prefira `rg` (ripgrep) para buscas rápidas; se indisponível, use `grep -Rni` com exclusões de diretórios (`.venv`, `.git`, caches). Exemplos: `rg -n "metrics|/metrics"`, `rg -n "collect_.*_task" market_alert`.
- **Commits**: mantenha mensagens claras no formato `<tipo>: <resumo>` do tipo de mudança (ex.: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`), sempre traga a frase utilizada para o commit ao final da resposta (Ex: feat: Add nova instrução ao AGENTS.md). Faça mudanças pequenas e coesas; referência arquivos/rotas afetadas. Evite criar branches sem necessidade ou renomear arquivos amplamente.
- **Alterações de interface**: evite quebras em contratos de API, schemas Pydantic ou assinaturas de tasks Celery. Preserve retrocompatibilidade e documente qualquer deprecação. e atualize `AGENTS.md`, `README.md` e testes.
- **Banco e migrações**: alterações de schema devem passar por Alembic; nunca execute deleções em massa sem salvaguardas.
- **Observabilidade**: registre logs estruturados, atualize métricas e revise alertas ou Prometheus quando necessário.
- **Segurança**: não exponha segredos. Utilize arquivos `.env` e helpers para acessar configurações.
- **Compatibilidade local/Docker**: mantenha portas alinhadas ao `docker-compose.yml`; evite conflitos.
- **Manutenção documental**: ao final de cada sprint ou mudança estrutural, sinalize ou execute atualizações necessárias em `README.md` e `AGENTS.md`.

## Interação entre serviços
- Comunicação frontend ⇄ backend via HTTP/JSON. O cliente padrão (`frontend/client/src/lib/api.ts`) injeta JWT no header `Authorization`.
- Workers Celery consomem filas `celery`, `scraping` e `monitor`, armazenando resultados no PostgreSQL e reprocessando comparações.
- O `ScraperClient` (`backend/market_alert/services/scraper_client.py`) envia requisições `POST /scraper/parse` ao `market_scraper`, que executa pipeline `FetchHTML → DomainSpecificParser → JsonLdParser → HtmlMetadataParser → GenericFallbackParser`.
- Resultados de scraping são persistidos e utilizados para calcular difusão de preços, disparar alertas e atualizar dashboards.

### Arquivos de ambiente (.env)
- O projeto utiliza três arquivos de configuração no `backend`:
  - `backend/.env.common` (raiz)
  - `backend/market_alert/.env.market_alert`
  - `backend/market_scraper/.env.market_scraper`
Carregamento: `backend/shared/core/config_base.py` carrega `./.env.common` e, por serviço, o arquivo `.env.<serviço>`.
- No `frontend` existe apenas um arquivo de configuração:
  - `frontend/.env`
 Em Docker, a variável `ENV_FILE` já aponta para o arquivo correto de cada serviço.
- Boas práticas: não commitar segredos; use valores dummy em exemplos; evite imprimir variáveis sensíveis em logs.

## Testes e qualidade
- Backend: `pytest backend/market_alert -q`, `pytest backend/market_scraper -q` e demais testes em `backend/shared/tests`.
- Frontend: `pnpm test` (quando configurado) e `pnpm lint`.
- Valide comandos em ambientes isolados e registre no relatório final as execuções realizadas.

## Checklist antes de concluir uma mudança
1. Atualize ou confirme a existência de docstrings/comentários relevantes em português.
2. Ajuste contratos, schemas ou métricas conforme necessário e estejam bem sincronizados com o projeto geral.
3. Execute testes pertinentes e registre resultados.
4. Valide se novas portas/variáveis foram documentadas.
5. Revise o `README.md` e demais READMEs específicos para garantir consistência.

## Manutenção contínua - AGENTS.md Atualizado
- Revisar este documento a cada sprint ou nova versão, e sempre que for realizado novas tarefas e mudanças no projeto.
- Documentar mudanças relevantes sempre que atualizar fluxos de autenticação, scraping, comparação, observabilidade ou arquitetura.
- Adicionar instruções sobre novos serviços, filas, métricas, variáveis de ambiente, pipelines ou convenções.
- Remover comandos desatualizados e alinhar com os READMEs específicos.
- Comparar o conteúdo com o `README.md` para evitar redundâncias: mantenha aqui instruções operacionais para agentes; no `README.md`, mantenha setup humano e visão geral.

> Nota: Um guia desatualizado prejudica a confiabilidade do agente e pode levar a ações incorretas.
