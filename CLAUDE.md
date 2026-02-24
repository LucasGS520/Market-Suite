# CLAUDE.md — market_alert

## Contexto da Fase Atual do Projeto

O módulo `market_alert` é o core do backend. Atualmente acumula ~8 domínios de responsabilidade em um único módulo, o que gera acoplamento alto, dificuldade de teste e comportamentos surpresa. O objetivo das tarefas aqui descritas é separar responsabilidades, aumentar confiança no código e reduzir complexidade.

### Principais Responsabilidades Problemáticas
Responsabilidades que devem ser refatoradas, reestruturadas, organizadas ou simplificadas, visando melhorar totalmente o módulo `market_alert`:
- Ciclo de vida dos produtos: CRUD de produtos monitorados e concorrentes, controle de status
- Orquestração de coletas: Fila de prioridade Redis, loop contínuo, despacho de tarefas Celery
- ~~Comparação de Preços~~: **CONCLUÍDO** — ver seção "Refatoração Completada" abaixo
- Persistência: Modelos ORM, operações CRUD, migrações alembic
- Infraestrutura: Configuração Celery, workers, Redis, CORS, rate limiting

---

## Problemas Conhecidos — Não Repita Esses Padrões

Ao sugerir ou escrever código neste projeto, evite os anti-padrões já existentes:

- **CRUD executando lógica de serviço**: arquivos `crud_*.py` não devem importar serviços, enfileirar no Redis ou tomar decisões de negócio. Devem apenas ler e escrever no banco.
- **Lógica de negócio em arquivos de dados**: funções como `_resolve_schedule_event` ou `_update_price_change_tracking` não pertencem a um arquivo CRUD. Regras de agendamento são responsabilidade da camada de serviço.
- **God Objects em services**: serviços não devem saber sobre filas, concorrentes, rate limiting e formatação de resposta ao mesmo tempo. Cada serviço deve ter uma responsabilidade clara.
- **Dois pontos de entrada para a mesma operação**: lógica de enfileiramento de scraping está duplicada entre `orchestrator/` e `continuous_dispatch.py`. Toda coleta deve passar por um único ponto de entrada.
- **`PriorityQueueService` importado diretamente por múltiplos módulos**: a fila Redis deve ser acessada apenas via orquestrador, nunca diretamente por serviços externos.
- **Tasks Celery como mini-aplicações**: a task deve ser uma casca fina que delega para um serviço. Validação, lock Redis, lógica de retry e agendamento não pertencem dentro da função da task.
- **Importações locais dentro de funções**: são sintoma de dependência circular. Se precisar fazer isso, a estrutura de módulos precisa ser reorganizada, não contornada.
- **Arquivo com 4+ responsabilidades**: consulta com autorização, reconstrução de resumo, persistência condicional e formatação de resposta não devem coexistir no mesmo arquivo.

---

## Refatoração Completada: Comparação de Preços

A responsabilidade "Comparação de Preços" foi extraída do `services_comparison.py` monolítico (1120 linhas) para 5 arquivos com responsabilidades únicas:

| Arquivo | O que faz |
|---------|-----------|
| `domain/price_competitiveness.py` | Lógica pura de competitividade — sem I/O, testável com pytest sozinho |
| `utils/snapshot_comparator.py` | Extrai campos materiais e detecta mudança real para evitar upserts redundantes |
| `services/services_comparison_utils.py` | Carregamento, filtragem canônica de concorrentes (única fonte de verdade para elegibilidade) |
| `services/services_comparison_calculator.py` | Agrega resultados em sumário, calcula insights, lida com inativos |
| `services/services_comparison.py` | Orquestrador enxuto: autoriza, carrega, calcula, persiste (~330 linhas vs 1120 anteriores) |

**Outras mudanças no mesmo PR:**
- `crud/crud_price_history.py`: adicionado `get_latest_price_for_competitor()` (fallback para comparação)
- `core/config_alert.py`: adicionados 3 limiares configuráveis (`COMPETITIVENESS_THRESHOLD_*_PCT`)
- `enums/enums_comparisons.py`: removido alias morto `NON_COMPETITIVE` (duplicava `ATTENTION`)
- `notifications/evaluator.py`: adicionado `validate_snapshot_contract()` e chamada defensiva em `evaluate()`

**Bugs corrigidos nesta refatoração:**
- Thresholds de competitividade corretos: `COMPETITIVE (≤0%) → ATTENTION (0–5%) → URGENT (>5%)`
- `should_refresh_competitors_count()` e `extract_competitors_count()` tornados públicos e movidos para módulos adequados

---

## Arquitetura Alvo

Adote separação clara em camadas. A direção de dependência deve ser:

```
API / Tasks (entrada)
    ↓
Services (orquestração e regras de negócio)
    ↓
Domain (lógica pura, sem I/O)
    ↓
CRUD (acesso a dados — burro, sem lógica)
    ↓
Models / ORM
```

**Regras da camada `domain/`:** Arquivos em `domain/` só importam stdlib, enums e dataclasses. Zero importações de services, crud, models ou infraestrutura. Isso garante testabilidade sem banco.

A fila Redis (`PriorityQueueService`) deve ser acessada exclusivamente via orquestrador. Nenhum serviço de domínio acessa a fila diretamente.

---

## Princípios para Este Projeto

- **Responsabilidade única**: cada arquivo tem um motivo para mudar
- **Dependências explícitas**: nenhuma operação de infraestrutura acontece implicitamente ao chamar uma função de domínio
- **Testabilidade**: qualquer serviço deve ser testável sem precisar simular Celery + Redis + banco simultaneamente
- **Ponto de entrada único**: operações críticas (enfileiramento, lock) têm exatamente um lugar no código
- **Módulo `market_alert`**: bem estruturado, limpo e organizado.

### Comportamento Esperado
- Sempre explique oque vai mudar ANTES de mudar
- Nunca altere mais de um arquivo por vez antes da minha confirmação
- Se achar bugs, problemas ou inconsistências, descreva-os antes de corrigir
- Use linguagem simples, para iniciantes em programação
- Se aparecer duvidas, pergunte antes de agir

> Nota: Ao final de cada sessão produtiva, proponha atualizações para o `CLAUDE.md` e documentações do projeto `README.md` com base noque foi realizado, garantindo que os arquivos sempre reflitam o estado real do projeto.
