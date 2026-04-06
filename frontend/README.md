# Frontend
SPA React responsavel pela experiencia web do Market Suite. O modulo concentra autenticacao, dashboard, listagem de monitorados, detalhe de produto, configuracoes e feedback visual do usuario, consumindo a API REST do `market_alert` via HTTP/JSON. O frontend nao fala diretamente com `market_scraper` nem com `market_orchestrator`; esses modulos aparecem apenas de forma indireta pelos contratos e estados retornados pela API principal.

## Relacoes e Referencias
- Visao arquitetural da suite: [`../README.md`](../README.md)
- API principal consumida pelo frontend: [`../backend/market_alert/README.md`](../backend/market_alert/README.md)
- Servico de scraping consumido indiretamente pela API: [`../backend/market_scraper/README.md`](../backend/market_scraper/README.md)
- Orquestrador duravel consumido indiretamente pela API: [`../backend/market_orchestrator/README.md`](../backend/market_orchestrator/README.md)

## Principais Responsabilidades
- **Expor a SPA principal do produto** com rotas publicas e protegidas para autenticacao, monitoramento e configuracoes.
- **Consumir a API REST do `market_alert`** com `axios`, `react-query` e tratamento centralizado de autenticacao.
- **Gerenciar sessao no navegador** mantendo `access_token` em memoria, `refresh` via cookie HttpOnly e cache leve do usuario em `sessionStorage`.
- **Renderizar estados operacionais do monitoramento** como disponibilidade, pausa, competitividade, timestamps e mensagens de erro.
- **Aplicar design system local** com MUI, tokens CSS, Tailwind e componentes reutilizaveis para a interface atual.

## Estrutura do Diretorio
```text
frontend/
|-- src/
|   |-- components/              # Layout, header, guards de rota e componentes reutilizaveis
|   |-- contexts/                # AuthContext e ToastContext
|   |-- hooks/                   # Hooks de auth, toast e debounce
|   |-- lib/                     # Cliente HTTP Axios e interceptors globais
|   |-- pages/                   # Telas da SPA (auth, dashboard, produtos, detalhe, settings)
|   |-- services/                # Camada de acesso a API por dominio
|   |-- types/                   # Tipos TypeScript para contratos consumidos
|   |-- utils/                   # Formatacao, status, tokens e helpers de renderizacao
|   |-- App.tsx                  # Providers globais, tema MUI e declaracao de rotas
|   |-- main.tsx                 # Bootstrap React/Vite
|   `-- index.css                # Tokens visuais globais, animacoes e reset
|-- public/                      # Assets publicos simples
|-- docs/                        # Documentacao visual complementar
|-- package.json                 # Scripts, dependencias e metadados do modulo
|-- vite.config.ts               # Dev server e proxy local
|-- tailwind.config.js           # Mapeamento do design system para utilitarios
|-- eslint.config.js             # Regras de lint para TS/React
|-- Dockerfile                   # Imagem Node para dev/build e stage de producao
`-- tsconfig*.json               # Configuracoes TypeScript do app e do tooling
```

---

## Rotas da SPA e Fluxos HTTP
As rotas sao registradas em [`src/App.tsx`](src/App.tsx) e protegidas por [`src/components/ProtectedRoute.tsx`](src/components/ProtectedRoute.tsx) quando exigem autenticacao. O modulo nao expoe endpoints HTTP proprios; ele consome os contratos do `market_alert`.

### Rotas mais relevantes
| Tipo | Rota SPA | Tela | Integracoes principais |
|------|----------|------|------------------------|
| Publica | `/login` | Login | `POST /auth/login`, `POST /auth/refresh`, `GET /users/me` |
| Publica | `/register` | Cadastro | `POST /users` e reenvio de verificacoes |
| Publica | `/verify-email` | Confirmacao de email | `POST /auth/verify-email` |
| Publica | `/verify-phone` | Confirmacao OTP de telefone | `POST /auth/verify-phone`, `POST /users/resend-verification` |
| Protegida | `/dashboard` | Resumo operacional | `GET /dashboard/stats`, `GET /monitored/featured` |
| Protegida | `/products` | Lista de monitorados | `GET /monitored`, `POST /monitored/scrape`, `PUT /monitored/{id}/paused`, `DELETE /monitored/{id}` |
| Protegida | `/product/:id` | Detalhe do monitorado | `GET /monitored/{id}`, `GET /competitors`, `POST /competitors/scrape`, `DELETE /competitors/{id}`, `GET /comparisons/{id}/summary` |
| Protegida | `/compare` | Comparacao global | tela placeholder no estado atual |
| Protegida | `/alerts` | Alertas/notificacoes | tela placeholder no estado atual |
| Protegida | `/settings` | Configuracoes do usuario | `GET/PATCH /settings/profile`, `GET/PATCH /settings/notifications` |

### Fluxos HTTP mais relevantes
- Sessao autenticada: o login envia `POST /auth/login`, guarda o `access_token` apenas em memoria e depende do refresh token em cookie HttpOnly para renovacao.
- Renovacao automatica: [`src/lib/api.ts`](src/lib/api.ts) intercepta `401`, chama `POST /auth/refresh` e reexecuta a request original quando possivel.
- Restauracao de sessao: [`src/contexts/AuthProvider.tsx`](src/contexts/AuthProvider.tsx) carrega o usuario com `GET /users/me`, agenda refresh com base no `exp` do JWT e limpa estado local se a sessao falhar.
- Monitoramento: a tela [`src/pages/Products.tsx`](src/pages/Products.tsx) lista monitorados com filtros/paginacao, cria novos itens via `POST /monitored/scrape` e sincroniza pause/resume/delete com a API.
- Detalhe e concorrentes: [`src/pages/ProductDetail.tsx`](src/pages/ProductDetail.tsx) combina detalhes do monitorado, resumo de comparacao e lista de concorrentes, com mutacoes de adicao/remocao.
- Configuracoes: [`src/pages/Settings.tsx`](src/pages/Settings.tsx) hoje sincroniza apenas perfil e preferencias globais de notificacao; demais secoes ainda sao visuais/placeholder.

## Dominios e Componentes Chave

### Shell, Providers e Roteamento
- [`src/App.tsx`](src/App.tsx) concentra `QueryClientProvider`, `ThemeProvider`, `AuthProvider`, `ToastProvider` e o roteamento principal com `BrowserRouter`.
- O tema atual usa MUI em modo escuro com acentos laranja/amarelo e sobrescritas de `Paper`, `Dialog`, `Popover` e superficies contextuais.
- [`src/main.tsx`](src/main.tsx) faz o bootstrap do React 19 com `createRoot` e `StrictMode`.
- [`src/components/Layout.tsx`](src/components/Layout.tsx) define o shell protegido com [`src/components/Header.tsx`](src/components/Header.tsx), container responsivo e banner de conta pendente.

### Autenticacao e Sessao
- [`src/contexts/AuthProvider.tsx`](src/contexts/AuthProvider.tsx) e a fonte de verdade da sessao no cliente: guarda usuario, token em memoria, loading inicial e metodos de login/logout/register/refresh.
- [`src/services/authService.ts`](src/services/authService.ts) encapsula login, logout, refresh, perfil atual, reset de senha e verificacoes de email/telefone.
- [`src/lib/api.ts`](src/lib/api.ts) configura `axios` com `withCredentials=true`, injecao do header `Authorization` e tentativa unica de refresh em respostas `401`.
- [`src/utils/authTokens.ts`](src/utils/authTokens.ts) abstrai armazenamento do `access_token` em memoria para reduzir persistencia local sensivel.
- [`src/components/ProtectedRoute.tsx`](src/components/ProtectedRoute.tsx) segura navegacao protegida enquanto o estado de autenticacao ainda esta sendo resolvido.

### Produtos, Competitividade e Dashboard
- [`src/services/productsService.ts`](src/services/productsService.ts) centraliza consultas e mutacoes de dashboard, monitorados, concorrentes e resumo de comparacao.
- O servico normaliza respostas do backend para evitar estados incoerentes de disponibilidade, `paused`, `last_checked`, `last_scraped_at` e badges de competitividade.
- [`src/pages/Dashboard.tsx`](src/pages/Dashboard.tsx) mostra cards operacionais e produtos em destaque, usando `react-query` para cache e estados de loading/erro.
- [`src/pages/Products.tsx`](src/pages/Products.tsx) usa query params (`view`, `q`, `status`, `page`) como fonte de verdade da navegacao da listagem.
- [`src/pages/ProductDetail.tsx`](src/pages/ProductDetail.tsx) agrega detalhe do monitorado, concorrentes, resumo de comparacao, acoes de pausa/exclusao e links externos para URLs monitoradas.

### Configuracoes, Feedback e Utilitarios
- [`src/pages/Settings.tsx`](src/pages/Settings.tsx) organiza as secoes de configuracao via query string `?section=...`.
- [`src/services/settingsService.ts`](src/services/settingsService.ts) sincroniza perfil e preferencias globais de notificacao com o backend.
- As secoes [`src/pages/settings/ProfileSection.tsx`](src/pages/settings/ProfileSection.tsx) e [`src/pages/settings/NotificationsSection.tsx`](src/pages/settings/NotificationsSection.tsx) possuem integracao real; `language`, `billing`, `help` e `about` ainda usam placeholders.
- [`src/contexts/ToastContext.tsx`](src/contexts/ToastContext.tsx) e [`src/hooks/useToast.ts`](src/hooks/useToast.ts) padronizam mensagens transientes de sucesso/erro na UI.
- [`src/utils/`](src/utils/) concentra formatacao monetaria/data, badges de status, truncamento de texto e helpers de renderizacao de preco.

### Design System e Tooling
- [`src/index.css`](src/index.css) define tokens globais de cor, espacamento, radius, sombra e animacoes do frontend atual.
- [`tailwind.config.js`](tailwind.config.js) mapeia esses tokens para utilitarios Tailwind; o projeto hoje combina Tailwind para primitives e MUI para componentes de interface.
- [`docs/open-surface-semantics.md`](docs/open-surface-semantics.md) documenta semantica visual complementar usada no frontend.
- [`eslint.config.js`](eslint.config.js) aplica lint moderno para TypeScript, hooks do React e integracao com Vite React Refresh.

---

## Fluxo de Trabalho

### 1. Boot da SPA e restauracao de sessao
1. O navegador carrega [`src/main.tsx`](src/main.tsx) e monta [`src/App.tsx`](src/App.tsx).
2. `AuthProvider` tenta restaurar usuario em cache e validar sessao consultando `GET /users/me`.
3. Se existir `access_token`, o provider agenda refresh automatico antes da expiracao.
4. Se a sessao falhar, o frontend limpa token/cache local e deixa apenas rotas publicas acessiveis.

### 2. Login, cadastro e verificacao
1. [`src/pages/Login.tsx`](src/pages/Login.tsx) envia `POST /auth/login`.
2. Em conta pendente, o frontend mantem o usuario autenticado e orienta verificacao de email/telefone.
3. [`src/pages/Register.tsx`](src/pages/Register.tsx) cria a conta com `POST /users`.
4. [`src/pages/VerifyEmail.tsx`](src/pages/VerifyEmail.tsx) confirma token de email e [`src/pages/VerifyPhone.tsx`](src/pages/VerifyPhone.tsx) valida OTP de telefone.

### 3. Gestao de produtos monitorados
1. [`src/pages/Products.tsx`](src/pages/Products.tsx) busca `GET /monitored` com filtros e paginacao.
2. A inclusao de um monitorado chama `POST /monitored/scrape` e atualiza o cache do React Query.
3. Acoes de pausa, retomada e exclusao sincronizam estado com `PUT /monitored/{id}/paused` e `DELETE /monitored/{id}`.
4. A URL preserva o contexto de busca/visualizacao para retorno consistente entre lista e detalhe.

### 4. Detalhe do monitorado e concorrentes
1. [`src/pages/ProductDetail.tsx`](src/pages/ProductDetail.tsx) carrega `GET /monitored/{id}`, `GET /competitors` e `GET /comparisons/{id}/summary`.
2. O usuario pode adicionar concorrentes via `POST /competitors/scrape`.
3. Remocoes usam `DELETE /competitors/{id}` e invalidam caches relacionados.
4. O frontend exibe disponibilidade, ultima coleta, badges de competitividade e links para as paginas originais dos produtos.

### 5. Configuracoes sincronizadas
1. [`src/pages/Settings.tsx`](src/pages/Settings.tsx) navega entre secoes sem recarregar a pagina.
2. `profile` consulta e atualiza `GET/PATCH /settings/profile`.
3. `notifications` consulta e atualiza `GET/PATCH /settings/notifications`.
4. Secoes `language`, `billing`, `help` e `about` ainda nao possuem backend nem persistencia propria.

---

## Configuracao

### Ordem de carregamento
1. [`src/lib/api.ts`](src/lib/api.ts) usa `import.meta.env.VITE_API_URL` quando definido.
2. Sem variavel, o fallback atual e `${location.protocol}//${location.hostname}:8000`.
3. Se a base configurada apontar para `localhost`, mas o frontend estiver sendo acessado por host remoto, o cliente substitui o hostname automaticamente.
4. [`vite.config.ts`](vite.config.ts) tambem mantem proxy de desenvolvimento para `/api`, hoje apontando para `http://192.168.15.150:8000`.

### Categorias de variaveis
| Categoria | Variavel | Uso |
|-----------|----------|-----|
| API | `VITE_API_URL` | Define a base URL consumida pelo cliente Axios em runtime |

## Operacao e Execucao

### Scripts principais
| Comando | Efeito |
|---------|--------|
| `pnpm dev` | Sobe o dev server Vite na porta `5173` |
| `pnpm build` | Executa `tsc -b` e gera build de producao com `vite build` |
| `pnpm preview` | Serve localmente a build gerada |
| `pnpm lint` | Executa ESLint no modulo |

### Docker atual
- [`Dockerfile`](Dockerfile) usa `node:20-alpine` com `corepack` e `pnpm`.
- O stage `builder` instala dependencias e copia o codigo, mas **nao executa `pnpm build`** no estado atual.
- O stage `production` espera `dist/` pronto e usa `serve -s dist -l 5173`, o que o torna mais proximo de um esqueleto para deploy futuro do que de uma imagem de producao finalizada.

---

## Pontos de Atencao Atuais
- [`src/pages/Compare.tsx`](src/pages/Compare.tsx) e [`src/pages/Alerts.tsx`](src/pages/Alerts.tsx) ainda sao placeholders sem integracao real com backend.
- Em [`src/pages/Settings.tsx`](src/pages/Settings.tsx), apenas `profile` e `notifications` possuem persistencia; as demais secoes sao visuais.
- O proxy de desenvolvimento em [`vite.config.ts`](vite.config.ts) usa IP fixo (`192.168.15.150:8000`), o que acopla o ambiente local atual.
- O cliente HTTP usa fallback baseado em `hostname:8000`; isso funciona bem em rede/local, mas exige alinhamento explicito em ambientes publicados.
- O `Dockerfile` de producao ainda depende de `dist/` previamente gerado, portanto nao representa um pipeline completo de build dentro da imagem.

## Fronteiras de Dominio

### Matriz de Responsabilidade
| Tema | Frontend | Backend |
|------|----------|---------|
| Navegacao, UX e estado visual | dono | apenas contratos consumidos |
| Sessao no browser | dono do estado local e refresh no cliente | dono da emissao/validacao de tokens |
| Regras de negocio de monitoramento | apenas apresenta e envia comandos | dono da regra, persistencia e execucao |
| Scraping e orquestracao | nao acessa diretamente | executado por `market_alert`, `market_scraper` e `market_orchestrator` |

### Regras Obrigatorias
- O frontend **nao replica regra de negocio critica** de monitoramento; no maximo normaliza payloads para exibicao segura.
- O frontend **nao acessa banco, Redis, Celery, Temporal ou scraper diretamente**.
- Contratos HTTP e estados exibidos devem seguir o que a API principal retorna; divergencias precisam ser resolvidas na fronteira de contrato, nao por acoplamento interno.
