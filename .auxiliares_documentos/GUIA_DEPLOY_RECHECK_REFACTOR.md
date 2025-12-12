# Guia de Deploy - Refatoração do Fluxo de Rechecagens

Este documento descreve o passo a passo para aplicar as mudanças da refatoração do fluxo de rechecagens em ambiente de produção/nuvem.

## Pré-requisitos

Antes de iniciar o deploy, certifique-se de:
- ✅ Ter acesso SSH ao servidor de produção
- ✅ Ter backup recente do banco de dados
- ✅ Ter monitoramento ativo (logs, métricas)
- ✅ Janela de manutenção planejada (recomendado)

## Opções de Deploy

### Opção 1: Deploy com Docker Compose (Recomendado)

Esta é a forma mais simples e segura se você já usa Docker Compose em produção.

#### Passo 1: Fazer backup do banco de dados

```bash
# Conectar ao servidor
ssh usuario@seu-servidor.com

# Fazer backup do PostgreSQL
docker exec market-suite-db-1 pg_dump -U postgres marketalert > backup_pre_recheck_$(date +%Y%m%d_%H%M%S).sql

# Verificar backup
ls -lh backup_*.sql
```

#### Passo 2: Atualizar o código

```bash
# Navegar até o diretório do projeto
cd /caminho/para/Market-Suite

# Fazer backup da branch atual (se houver mudanças locais)
git stash

# Buscar as últimas mudanças
git fetch origin

# Fazer checkout da branch com as mudanças
git checkout copilot/refactor-rechecking-collection-flow

# Ou se já foi mergeado na main:
# git checkout main
# git pull origin main
```

#### Passo 3: Aplicar a migração do banco de dados

```bash
# Parar os workers e beat (para evitar conflitos durante migração)
docker-compose stop celery-worker celery-beat

# Aplicar migração
docker-compose exec market_alert alembic -c /app/market_alert/alembic.ini upgrade head

# Ou se preferir rodar diretamente:
cd backend/market_alert
docker-compose run --rm market_alert alembic upgrade head
```

**Verificar migração:**
```bash
# Conectar ao banco para confirmar
docker exec -it market-suite-db-1 psql -U postgres -d marketalert

# Executar query de verificação
SELECT column_name 
FROM information_schema.columns 
WHERE table_name = 'monitored_products' 
  AND column_name IN ('checking_in_progress', 'checking_started_at');

# Deve retornar vazio (0 rows)

# Sair do psql
\q
```

#### Passo 4: Reconstruir e reiniciar os serviços

```bash
# Reconstruir imagens (se necessário)
docker-compose build market_alert celery-worker celery-beat

# Reiniciar todos os serviços do backend
docker-compose restart market_alert market_scraper celery-worker celery-beat

# Ou reiniciar tudo:
docker-compose down
docker-compose up -d
```

#### Passo 5: Validar o funcionamento

```bash
# 1. Verificar logs do Beat (deve rodar a cada 5min)
docker-compose logs -f celery-beat | grep "schedule_rechecks\|scheduler_dispatched"

# 2. Verificar logs do Worker (deve processar coletas)
docker-compose logs -f celery-worker | grep "collect_product_finished"

# 3. Verificar saúde dos serviços
docker-compose ps

# 4. Testar endpoint de saúde da API
curl http://localhost:8000/health
```

#### Passo 6: Monitorar métricas (opcional, mas recomendado)

```bash
# Acessar Prometheus (se disponível)
# http://seu-servidor:9090

# Queries úteis:
# rate(recheck_dispatch_total[5m])
# collector_success_total{kind="monitored"}
# scraping_latency_seconds{source="recheck_scheduler"}
```

---

### Opção 2: Deploy Manual (sem Docker)

Se você roda os serviços diretamente no servidor (sem Docker).

#### Passo 1: Backup e preparação

```bash
# Conectar ao servidor
ssh usuario@seu-servidor.com

# Backup do banco
pg_dump -U postgres marketalert > backup_pre_recheck_$(date +%Y%m%d_%H%M%S).sql

# Navegar até o projeto
cd /caminho/para/Market-Suite
```

#### Passo 2: Atualizar código

```bash
# Backup local
git stash

# Atualizar repositório
git fetch origin
git checkout copilot/refactor-rechecking-collection-flow
# ou: git checkout main && git pull
```

#### Passo 3: Ativar ambiente virtual e atualizar dependências

```bash
# Ativar venv
source .venv/bin/activate  # ou: source venv/bin/activate

# Atualizar dependências (se houver mudanças)
pip install -r requirements.txt
pip install -r backend/market_alert/requirements.txt
```

#### Passo 4: Parar serviços

```bash
# Parar workers e beat
sudo systemctl stop celery-worker
sudo systemctl stop celery-beat

# Ou se usando supervisord:
# supervisorctl stop celery_worker
# supervisorctl stop celery_beat
```

#### Passo 5: Aplicar migração

```bash
cd backend/market_alert
alembic upgrade head

# Verificar sucesso
alembic current
```

#### Passo 6: Reiniciar serviços

```bash
# Reiniciar API
sudo systemctl restart market-alert-api

# Reiniciar workers e beat
sudo systemctl start celery-worker
sudo systemctl start celery-beat

# Verificar status
sudo systemctl status celery-worker
sudo systemctl status celery-beat
```

#### Passo 7: Validar

```bash
# Logs do Beat
sudo journalctl -u celery-beat -f | grep "scheduler_dispatched"

# Logs do Worker
sudo journalctl -u celery-worker -f | grep "collect_product_finished"

# Health check
curl http://localhost:8000/health
```

---

### Opção 3: Deploy em Nuvem (AWS, Azure, GCP, etc.)

O processo varia conforme a plataforma, mas os princípios são os mesmos:

#### AWS ECS/Fargate

```bash
# 1. Fazer backup do RDS
aws rds create-db-snapshot --db-instance-identifier market-suite-prod --db-snapshot-identifier market-suite-backup-$(date +%Y%m%d)

# 2. Atualizar imagem Docker no ECR
docker build -t market-suite-api:latest -f backend/market_alert/Dockerfile .
docker tag market-suite-api:latest <sua-conta>.dkr.ecr.<regiao>.amazonaws.com/market-suite-api:latest
docker push <sua-conta>.dkr.ecr.<regiao>.amazonaws.com/market-suite-api:latest

# 3. Aplicar migração (usando task temporária ou connection direto ao RDS)
aws ecs run-task \
  --cluster market-suite-cluster \
  --task-definition market-alert-migration \
  --overrides '{"containerOverrides": [{"name": "migration", "command": ["alembic", "upgrade", "head"]}]}'

# 4. Atualizar serviços ECS
aws ecs update-service --cluster market-suite-cluster --service market-alert-api --force-new-deployment
aws ecs update-service --cluster market-suite-cluster --service celery-worker --force-new-deployment
aws ecs update-service --cluster market-suite-cluster --service celery-beat --force-new-deployment
```

#### Azure Container Instances / App Service

```bash
# 1. Backup do Azure Database for PostgreSQL
az postgres flexible-server backup create \
  --resource-group market-suite-rg \
  --server-name market-suite-db \
  --name backup-pre-recheck-$(date +%Y%m%d)

# 2. Atualizar imagem no ACR
docker build -t market-suite-api:latest .
docker tag market-suite-api:latest <seu-registry>.azurecr.io/market-suite-api:latest
docker push <seu-registry>.azurecr.io/market-suite-api:latest

# 3. Aplicar migração (via container temporário)
az container create \
  --resource-group market-suite-rg \
  --name migration-runner \
  --image <seu-registry>.azurecr.io/market-suite-api:latest \
  --command-line "alembic upgrade head" \
  --restart-policy Never

# 4. Atualizar App Services
az webapp restart --name market-alert-api --resource-group market-suite-rg
az webapp restart --name celery-worker --resource-group market-suite-rg
az webapp restart --name celery-beat --resource-group market-suite-rg
```

#### Google Cloud Run / GKE

```bash
# 1. Backup do Cloud SQL
gcloud sql backups create --instance=market-suite-db

# 2. Build e push para GCR
docker build -t gcr.io/<seu-projeto>/market-suite-api:latest .
docker push gcr.io/<seu-projeto>/market-suite-api:latest

# 3. Aplicar migração (via Cloud Run Job)
gcloud run jobs create migration-runner \
  --image gcr.io/<seu-projeto>/market-suite-api:latest \
  --command alembic,upgrade,head

gcloud run jobs execute migration-runner

# 4. Deploy nova versão
gcloud run deploy market-alert-api --image gcr.io/<seu-projeto>/market-suite-api:latest
gcloud run deploy celery-worker --image gcr.io/<seu-projeto>/market-suite-api:latest
```

---

## Validação Pós-Deploy

Execute estas verificações após o deploy em **qualquer** ambiente:

### 1. Verificar Banco de Dados

```sql
-- Conectar ao PostgreSQL
psql -U postgres -d marketalert

-- Confirmar que colunas foram removidas
SELECT column_name 
FROM information_schema.columns 
WHERE table_name = 'monitored_products' 
  AND column_name IN ('checking_in_progress', 'checking_started_at');
-- Deve retornar 0 linhas

-- Verificar que next_check_at está sendo atualizado
SELECT id, name_identification, next_check_at, last_checked, last_scraped_at
FROM monitored_products
WHERE monitoring_type = 'scraping'
ORDER BY last_checked DESC NULLS LAST
LIMIT 10;

-- Produtos devem ter next_check_at no futuro após coletas
```

### 2. Verificar Logs

```bash
# Logs do scheduler (deve executar a cada 5 minutos)
# Procurar por: "scheduler_dispatched"
grep "scheduler_dispatched" /var/log/celery-beat.log

# Logs de coletas (devem processar normalmente)
# Procurar por: "collect_product_finished"
grep "collect_product_finished" /var/log/celery-worker.log
```

### 3. Verificar Métricas (se Prometheus disponível)

Acesse o Prometheus e execute:

```promql
# Taxa de dispatch de rechecks (deve ser > 0 a cada 5min)
rate(recheck_dispatch_total[10m])

# Sucessos de coleta
rate(collector_success_total{kind="monitored"}[10m])

# Latência do scheduler
scraping_latency_seconds{source="recheck_scheduler"}
```

### 4. Teste Funcional

```bash
# 1. Criar um produto monitorado via API
curl -X POST http://seu-servidor:8000/api/v1/monitored \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name_identification": "Produto Teste Deploy",
    "product_url": "https://www.amazon.com.br/dp/B08N5WRWNW"
  }'

# 2. Aguardar 5-10 minutos

# 3. Verificar que o produto foi coletado
curl http://seu-servidor:8000/api/v1/monitored | jq '.[] | select(.name_identification == "Produto Teste Deploy")'

# 4. Confirmar que next_check_at foi atualizado
```

---

## Troubleshooting

### Problema: Migração falha com erro de coluna não encontrada

**Causa:** Migração já foi aplicada anteriormente

**Solução:**
```bash
# Verificar histórico de migrações
alembic current

# Se já estiver na versão f8d9e2a1b3c4, está ok
# Caso contrário, rodar:
alembic upgrade head
```

### Problema: Workers não estão processando rechecks

**Verificar:**
```bash
# 1. Beat está rodando?
docker-compose ps celery-beat
# ou: systemctl status celery-beat

# 2. Workers estão consumindo fila "scraping"?
docker-compose logs celery-worker | grep "scraping"

# 3. Produtos têm next_check_at definido?
# Conectar ao banco e verificar:
SELECT COUNT(*) FROM monitored_products WHERE next_check_at IS NULL;
```

**Solução:** Se muitos produtos sem `next_check_at`, rodar script de correção:

```sql
-- Atualizar produtos sem next_check_at
UPDATE monitored_products
SET next_check_at = NOW() + INTERVAL '5 minutes'
WHERE next_check_at IS NULL
  AND monitoring_type = 'scraping';
```

### Problema: Produtos parecem "travados"

**Causa:** Isso não deve mais acontecer (flag foi removida), mas pode ser lock Redis preso

**Solução:**
```bash
# Conectar ao Redis
docker exec -it market-suite-redis-1 redis-cli

# Verificar locks ativos
KEYS product_lock:*

# Se necessário, remover locks manualmente (use com cuidado!)
DEL product_lock:<product_id>
```

---

## Rollback

Se algo der errado, siga este procedimento:

### 1. Reverter código

```bash
# Se usando Docker Compose
cd /caminho/para/Market-Suite
git checkout <commit-antes-da-refatoracao>
docker-compose build
docker-compose restart market_alert celery-worker celery-beat
```

### 2. Reverter migração do banco

```bash
# Reverter uma migração
cd backend/market_alert
alembic downgrade -1

# Verificar
alembic current
```

### 3. Restaurar backup (se necessário)

```bash
# Restaurar backup do PostgreSQL
docker exec -i market-suite-db-1 psql -U postgres marketalert < backup_pre_recheck_YYYYMMDD_HHMMSS.sql

# Reiniciar serviços
docker-compose restart market_alert celery-worker celery-beat
```

---

## Checklist Final

Antes de considerar o deploy concluído:

- [ ] Backup do banco de dados realizado
- [ ] Código atualizado para a branch correta
- [ ] Migração aplicada com sucesso (`alembic current` mostra `f8d9e2a1b3c4`)
- [ ] Serviços reiniciados (API, workers, beat)
- [ ] Logs do Beat mostram `scheduler_dispatched` a cada 5min
- [ ] Logs do Worker mostram `collect_product_finished`
- [ ] Banco de dados não tem mais colunas `checking_in_progress` e `checking_started_at`
- [ ] Produtos estão sendo coletados normalmente
- [ ] Campo `next_check_at` está sendo atualizado após coletas
- [ ] Métricas Prometheus (se disponível) mostram atividade normal
- [ ] Teste funcional passou (criar produto → aguardar → verificar coleta)

---

## Suporte

Se encontrar problemas durante o deploy:

1. **Verifique logs detalhados:**
   ```bash
   docker-compose logs --tail=100 celery-beat celery-worker market_alert
   ```

2. **Consulte a documentação:**
   - `.auxiliares_documentos/REFACTORING_RECHECK_FLOW.md` - Detalhes técnicos
   - `README.md` - Visão geral
   - `AGENTS.md` - Guia operacional

3. **Rollback se necessário:** Não hesite em reverter se algo crítico falhar

---

**Data:** 2025-12-12  
**Versão:** 1.0  
**Status:** Pronto para produção ✅
