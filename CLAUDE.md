# CLAUDE.md — market_alert

## Docker — Decisões e Aprendizados

### Estrutura de requirements
- `requirements-base.txt` na raiz do projeto: dependências compartilhadas entre `market_alert` e `market_scraper`
- Cada módulo tem seu próprio `requirements-market-*.txt` com pacotes específicos
- Dockerfiles usam `COPY --from=root` (via `additional_contexts` no docker-compose) para acessar a raiz

### Build com BuildKit
- Todos os Dockerfiles usam `--mount=type=cache,target=/root/.cache/pip`
- O `docker-compose.yml` declara `additional_contexts: root: .` nos 7 serviços que precisam de `requirements-base.txt`
- Frontend usa Dockerfile multi-stage: `builder` (dev com Vite) e `production` (serve estático)
- O stage `builder` instala dependências no build — restart do container não reinstala pacotes

### Scripts úteis
- `.\scripts\docker-cleanup.ps1` — limpa volumes, imagens e cache de build (Windows)
- `bash scripts/docker-monitor.sh` — monitora CPU/RAM dos containers em tempo real

### O que NÃO mudar no docker-compose
- Volumes `./frontend:/app` + `frontend-node-modules:/app/node_modules`: padrão necessário para hot-reload + node_modules do Dockerfile coexistirem
- `additional_contexts: root: .` em todos os serviços que referenciam `requirements-base.txt`
- `target: builder` no serviço `frontend`: garante que a etapa de produção (com `pnpm build`) não seja executada em dev

## Desenvolvimento Local (Recomendado para Dev)

Para máxima velocidade com hot-reload local:

- **Docker rodando apenas infraestrutura** (PostgreSQL + Redis)
- **API, Workers e Frontend rodando localmente** em Python/Node nativos
- Veja [DEVELOPMENT.md](DEVELOPMENT.md) para setup completo

**Quick start:**
```bash
# Terminal 1: Infraestrutura
docker-compose -f docker-compose.infra-only.yml up

# Setup uma vez
bash scripts/dev-setup.sh

# Terminais 2-6: Componentes locais
bash scripts/dev-migrate.sh
bash scripts/dev-start-api.sh
bash scripts/dev-start-workers.sh scraping
bash scripts/dev-start-workers.sh monitor
bash scripts/dev-start-workers.sh beat
bash scripts/dev-start-frontend.sh
```

---

## Docker Profiles — Ligar/Desligar Blocos

O compose utiliza `profiles` para separar responsabilidades e permitir rodar subsets independentes:

### Perfis Disponíveis

| Perfil | Serviços | Caso de Uso |
|--------|----------|-----------|
| `infra` | `db`, `redis`, `redis-init` | Database + cache (base obrigatória) |
| `api` | `migrations`, `market_alert` | API principal + migrações |
| `workers` | `celery-worker-{scraping,monitor,compare,notifications}` | Processamento assíncrono |
| `scraper` | `market_scraper` | Serviço de scraping externo |
| `ui` | `frontend` | Interface web (Vite) |

### Exemplos de Uso

```bash
# Apenas infraestrutura (para setup inicial ou testes de conexão)
docker-compose --profile infra up

# API completa (infra é automático via depends_on)
docker-compose --profile infra --profile api up

# Full-stack em desenvolvimento
docker-compose --profile infra --profile api --profile workers --profile ui up

# Produção sem UI (API + workers + scraper, sem frontend)
docker-compose --profile infra --profile api --profile workers --profile scraper up

# Apenas workers (útil para escalar processamento separado)
docker-compose --profile infra --profile workers up

# Scraper isolado para testes
docker-compose --profile infra --profile scraper up
```

### Ordem de Inicialização Garantida

Mesmo com profiles, as dependências via `depends_on` com healthchecks/completion são respeitadas:

1. **Infra**: `db` e `redis` iniciam em paralelo
2. **Redis-init**: Aguarda `redis:healthy`, carrega scripts Lua, completa
3. **API**: `migrations` espera `db:healthy`, depois `market_alert` espera `db:healthy` + `redis:healthy` + `redis-init:completed`
4. **Workers/Scraper**: Aguardam `db:healthy` + `redis:healthy` + `redis-init:completed` (não bloqueados por API)
5. **UI**: Aguarda `market_alert:healthy` (agora com healthcheck implementado)
