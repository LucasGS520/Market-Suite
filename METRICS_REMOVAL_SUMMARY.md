# Remoção de Métricas e Observabilidade - Resumo Técnico

Data: 2026-02-03

## Objetivo
Remover o sistema de métricas Prometheus e observabilidade (Grafana, Loki) do Market Suite, mantendo a aplicação funcional através de stubs no-op.

## Estratégia Implementada

### 1. Stubs No-Op
Criados dois módulos de stub que simulam a API do prometheus_client sem realizar operações reais:

- **`backend/shared/metrics/_noop_metrics.py`**: Classes `Counter`, `Gauge`, `Histogram`, `Summary`
- **`backend/shared/metrics/_noop_prometheus_client.py`**: Funções `generate_latest()`, `start_http_server()`, `REGISTRY`

Todos os 18 arquivos `metrics_*.py` foram atualizados para importar dos stubs em vez do prometheus_client.

### 2. Compatibilidade de API Mantida
- Todas as importações existentes continuam funcionando: `from shared.metrics import HTTP_REQUESTS_TOTAL`
- Todas as operações continuam válidas: `.inc()`, `.dec()`, `.set()`, `.observe()`, `.labels()`
- Nenhuma mudança necessária em código que usa métricas
- Endpoint `/metrics` continua disponível mas retorna vazio

### 3. Dependências Removidas
**backend/market_alert/requirements.txt:**
- ❌ `prometheus-fastapi-instrumentator==7.1.0`
- ❌ `prometheus_client==0.21.1`

**backend/market_scraper/requirements.txt:**
- ❌ `prometheus-client==0.21.1`

### 4. Infraestrutura Simplificada

**Removido de docker-compose.yml (88 linhas):**
- ❌ prometheus (servidor de métricas)
- ❌ grafana (visualização)
- ❌ loki (agregação de logs)
- ❌ promtail (coletor de logs)
- ❌ node-exporter (métricas de host)
- ❌ cadvisor (métricas de containers)

**Mantidos:**
- ✅ PostgreSQL
- ✅ Redis
- ✅ market_alert (API + workers)
- ✅ market_scraper
- ✅ frontend

### 5. Arquivos Removidos

**Diretórios:**
- `backend/shared/infra/monitoring/` (13 dashboards Grafana + configs)

**Testes:**
- `backend/market_alert/tests/unit/tasks/test_metrics_tasks.py`
- `backend/shared/tests/unit/test_metrics_parser.py`
- `backend/shared/tests/unit/test_metrics_prometheus.py`
- `backend/market_scraper/tests/integration/routes/test_parse.py` (dependia de validação de métricas)

### 6. Arquivos Modificados

**Principais entradas da aplicação:**
- `backend/market_alert/main.py` - substituído import prometheus_client
- `backend/market_scraper/main.py` - substituído import prometheus_client
- `backend/market_alert/beat_with_metrics.py` - substituído import prometheus_client
- `backend/market_alert/core/celery_app.py` - substituído import prometheus_client

**Todos os módulos de métricas (18 arquivos):**
- `metrics_api.py`, `metrics_audit.py`, `metrics_auth.py`, etc.
- Trocado `from prometheus_client import` → `from ._noop_metrics import`

### 7. Arquivos Preservados

**Mantidos funcionais (com stubs no-op):**
- ✅ `backend/market_alert/tasks/metrics_tasks.py` - tasks de coleta continuam existindo, apenas não coletam dados reais
- ✅ Todos os arquivos em `backend/shared/metrics/` - mantidos para compatibilidade de API
- ✅ Imports de métricas em services, orchestrators, utils - continuam funcionando sem mudanças

## Backup Realizado

Dois diretórios de backup foram criados (ignorados no .gitignore):
- `metrics_backup/` - cópia completa de todos os 18 arquivos originais de métricas
- `monitoring_backup/` - cópia dos dashboards Grafana e configurações

Inventário completo documentado em `METRICS_INVENTORY.md` (também ignorado no .gitignore).

## Impactos

### ✅ Impactos Positivos
1. **Redução de complexidade**: 88 linhas removidas do docker-compose.yml
2. **Menos dependências**: 3 bibliotecas removidas dos requirements
3. **Startup mais rápido**: não inicia serviços prometheus/grafana/loki
4. **Menor uso de recursos**: ~3-4 containers a menos rodando
5. **Zero mudanças de código necessárias**: stubs mantêm compatibilidade

### ⚠️ Impactos Negativos
1. **Sem observabilidade centralizada**: não há mais coleta de métricas
2. **Sem dashboards**: visualizações Grafana não disponíveis
3. **Sem agregação de logs**: Loki não está mais coletando logs
4. **Endpoint /metrics vazio**: retorna vazio em vez de métricas Prometheus

## Código de Exemplo

### Antes (com Prometheus)
```python
from prometheus_client import Counter
API_ERRORS_TOTAL = Counter("api_errors_total", "Total de erros", ["service"])
API_ERRORS_TOTAL.labels(service="market_alert").inc()
```

### Depois (com stubs no-op)
```python
from ._noop_metrics import Counter
API_ERRORS_TOTAL = Counter("api_errors_total", "Total de erros", ["service"])
API_ERRORS_TOTAL.labels(service="market_alert").inc()  # Não faz nada, mas não quebra
```

O código é **idêntico**, apenas o import mudou internamente nos arquivos de métricas.

## Validação

### Testes Executados
```bash
# Validação de imports
python3 -c "from shared.metrics import HTTP_REQUESTS_TOTAL, LOG_ENTRIES_TOTAL; print('OK')"

# Validação de operações no-op
python3 -c "from shared.metrics import HTTP_REQUESTS_TOTAL; \
  HTTP_REQUESTS_TOTAL.labels(service='test', method='GET', endpoint='/', status_code=200).inc(); \
  print('OK')"

# Validação de prometheus_client stubs
python3 -c "from shared.metrics._noop_prometheus_client import generate_latest, REGISTRY; \
  result = generate_latest(REGISTRY); \
  assert result == b''; \
  print('OK')"
```

Todos os testes passaram com sucesso. ✅

## Reversão

Para reverter as mudanças (se necessário):
1. Restaurar arquivos de `metrics_backup/` para `backend/shared/metrics/`
2. Restaurar arquivos de `monitoring_backup/` para `backend/shared/infra/monitoring/`
3. Restaurar versões anteriores de `main.py`, `beat_with_metrics.py`, etc do git
4. Restaurar dependências nos `requirements.txt`
5. Descomentar serviços no `docker-compose.yml` (ou restaurar do git)

## Próximos Passos Recomendados

Se a remoção for permanente:
1. ✅ Remover diretórios de backup após validação em staging/produção
2. ✅ Considerar remoção completa dos arquivos de métricas (não apenas stubs)
3. ✅ Avaliar se `metrics_tasks.py` e tasks de coleta de métricas podem ser removidas
4. ⚠️ Implementar alternativa leve de logging estruturado, se necessário
5. ⚠️ Documentar em CHANGELOG.md quando for para produção

## Documentação Atualizada

- ✅ `AGENTS.md` - removidas todas as referências a Prometheus, Grafana, Loki e métricas específicas
- ⏳ `README.md` - pendente
- ⏳ `backend/market_alert/README.md` - pendente
- ⏳ `backend/market_scraper/README.md` - pendente

## Conclusão

A remoção de métricas e observabilidade foi concluída com sucesso utilizando uma abordagem de **stubs no-op**, que:
- ✅ Mantém compatibilidade total de API
- ✅ Não requer mudanças em código consumidor
- ✅ Permite reversão rápida se necessário
- ✅ Reduz significativamente a complexidade da infraestrutura
- ✅ Elimina dependências externas de observabilidade

O sistema continua funcional e todos os imports de métricas continuam válidos, apenas não coletam dados reais.
