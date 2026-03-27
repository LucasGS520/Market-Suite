# Claude — Correção Camada de Inicialização

## Sobre o Projeto *Market Suite* (`market_suite`)
**MarketSuite** é uma plataforma de monitoramento e comparação de preços em e-commerce. Usuários cadastram produtos que desejam acompanhar, o sistema coleta informações de preço e disponibilidade automaticamente, compara com concorrentes e dispara notificações quando mudanças significativas são detectadas.

O projeto é separado por responsabilidades, em diferentes módulos:
**Backend**:
- **API + Persistência** (market_alert): Gerencia estado de usuários, produtos, comparações
- **Scraping especializado** (market_scraper): Extrai dados de e-commerce via HTTP
- **Processamento em background** (Celery + Redis): Coleta, comparação e notificações assíncronas
- **Orquestração durável** (market_orchestrator): Ciclo de vida contínuo de monitoramento por produto com Temporal.

**Frontend**:
- **SPA moderna**: consome API backend via HTTP (REST/JSON).

> Informações sobre a Stack e Tecnologias existentes em [STACK_MARKET.md](STACK_MARKET.md)

---

## Objetivo e Estratégias

**Objetivo:** 
Alinhar o frontend atual do `market_suite` ao DNA visual do design ideal, criando um design system oficial original, consistente e implementável com React + TypeScript + MUI + Tailwind, sem alterar estrutura funcional, conexão com APIs, autenticação e integrações já existentes.

**Estratégia de Implementação:** 
Executar em fases incrementais, começando por fundação de design tokens e tema unificado, depois migrar componentes e páginas prioritárias, e por fim validar qualidade (UX, acessibilidade, performance e regressão visual). O rollout será progressivo, com baixo risco e sem refatoração de arquitetura de aplicação.

---

## Análise de Riscos e Decisões Chave
**Decisão Técnica Principal:** adotar uma camada única de tokens como “fonte da verdade” e propagar para:
- tema MUI (`createTheme`),
- configuração Tailwind (`theme.extend`),
- variáveis globais CSS.

**Risco Principal:** inconsistência visual por dupla fonte de estilo (MUI + Tailwind) e legado de estilos globais.
- Mitigação: definir matriz de precedência de estilos, checklist de migração por componente e auditoria de classes utilitárias versus props de tema MUI.

**Dependências:**
- Stack atual confirmada: React + TypeScript + Vite + MUI + Tailwind.
- Compatibilidade com estrutura atual de páginas, componentes e providers.
- Ambiente de build/lint existente do frontend.
- Documento de stack (STACK_MARKET.md) como referência de limites técnicos.

---

## Regras e Instruções de Execução
**Regras obrigatórias de economia (NÃO IGNORAR)**
1) NÃO liste árvore inteira do projeto (evite `tree`, `ls -R`, etc.). Se precisar, liste apenas pastas-alvo da FASE.
2) NÃO leia arquivos completos. Leia no máximo 120 linhas por arquivo (ou trechos específicos). Se precisar de mais contextualização, peça antes.
3) Priorize busca (rg/grep) para localizar pontos de mudança antes de abrir arquivos.
5) Não cole conteúdo integral de arquivos na resposta. Mostre apenas:
   - arquivos alterados
   - resumo do diff (o que mudou e por quê)
   - comandos executados e resultados
6) Execute somente UMA FASE por vez. Ao terminar a FASE:
   - pare e peça autorização para a próxima FASE
7) Se detectar duplicação/overreach fora do escopo, interrompa e reporte.
