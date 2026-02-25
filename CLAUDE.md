# CLAUDE.md — market_alert

## Contexto da Fase Atual do Projeto

O módulo `market_alert` é o core do backend. Atualmente acumula ~8 domínios de responsabilidade em um único módulo, o que gera acoplamento alto, dificuldade de teste e comportamentos surpresa. 
O objetivo das tarefas aqui descritas é separar responsabilidades, aumentar confiança no código e reduzir complexidade.

### Principais Responsabilidades Problemáticas
Responsabilidades que devem ser refatoradas, reestruturadas, organizadas ou simplificadas, visando melhorar totalmente o módulo `market_alert`:
- Infraestrutura: Configuração Celery, workers, Redis, CORS, rate limiting

---

## Problemas Conhecidos — Não Repita Esses Padrões

Ao sugerir ou escrever código neste projeto, evite os anti-padrões já existentes:

- **Tasks Celery como mini-aplicações**: a task deve ser uma casca fina que delega para um serviço. Validar/obter payload, abrir sessão, setar trace_id, chamar service(s) passando `db: Session`, tratar erros/retries e encerrar sessão
- **Services**: recebem `db: Session` (não chamam `SessionLocal()` internamente) e orquestram chamadas a CRUD/domain. Services podem optar por confirmar (commit) via CRUD helpers, mas não devem criar sessões.
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
Domain (lógica pura, sem I/O)
    ↓
CRUD (acesso a dados — burro, sem lógica)
    ↓
Models / ORM
```

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
