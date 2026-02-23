# CLAUDE.md — market_alert

## Contexto da Fase Atual do Projeto

O módulo `market_alert` é o core do backend. Atualmente acumula ~8 domínios de responsabilidade em um único módulo, o que gera acoplamento alto, dificuldade de teste e comportamentos surpresa. O objetivo das tarefas aqui descritas é separar responsabilidades, aumentar confiança no código e reduzir complexidade.

### Principais Responsabilidades Problemáticas 
Responsabilidades que devem ser refatoradas, reestruturadss, organizadas ou simplificadas, visando melhorar totalmente o módulo `market_alert`:
- Ciclo de vida dos produtos: CRUD de produtos monitorados e concorrentes, controle de status
- Orquestração de coletas: Fila de prioridade Redis, loop contínuo, despacho de tarefas Celery
- Comparação de Preços: Calcular competitividade, construir sumários, persistir resultados
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

## Arquitetura Alvo

Adote separação clara em camadas. A direção de dependência deve ser:

```
API / Tasks (entrada)
    ↓
Services (orquestração e regras de negócio)
    ↓
CRUD (acesso a dados — burro, sem lógica)
    ↓
Models / ORM
```

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
