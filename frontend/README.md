# MarketAlert Frontend

Frontend moderno e responsivo para o sistema de monitoramento inteligente de preços **MarketAlert**, construído com **React**, **Vite**, **TypeScript**, **Tailwind CSS** e **Radix UI**.

## Visão Geral

O MarketAlert Frontend fornece uma interface intuitiva para monitorar preços de produtos no Mercado Livre, Amazon e Magazine Luiza, comparar com concorrentes e receber alertas automáticos sobre mudanças de preço. O sistema permite que vendedores gerenciem múltiplos produtos, acompanhem a concorrência e otimizem suas estratégias de precificação.

## Stack Tecnológico

- **Frontend Framework:** React 18 + TypeScript
- **Build Tool:** Vite
- **Styling:** Tailwind CSS 4 + Radix UI
- **Routing:** Wouter
- **HTTP Client:** Fetch API nativa
- **State Management:** React Context + Hooks
- **UI Components:** Radix UI + shadcn/ui
- **Icons:** Lucide React
- **Notifications:** Sonner

## Estrutura do Projeto

```
client/
├── public/              # Arquivos estáticos
├── src/
│   ├── components/      # Componentes reutilizáveis
│   │   ├── Header.tsx
│   │   ├── Navigation.tsx
│   │   ├── DashboardLayout.tsx
│   │   ├── ProtectedRoute.tsx
│   │   ├── StatsCard.tsx
│   │   └── ui/          # Componentes Radix UI
│   ├── contexts/        # React Contexts
│   │   ├── AuthContext.tsx
│   │   └── ThemeContext.tsx
│   ├── hooks/           # Hooks customizados
│   │   ├── useMonitoredProducts.ts
│   │   ├── useAlerts.ts
│   │   └── ...
│   ├── lib/             # Utilitários e cliente API
│   │   └── api.ts
│   ├── pages/           # Páginas da aplicação
│   │   ├── Login.tsx
│   │   ├── Dashboard.tsx
│   │   ├── Products.tsx
│   │   ├── AddProduct.tsx
│   │   ├── Alerts.tsx
│   │   ├── Settings.tsx
│   │   └── NotFound.tsx
│   ├── App.tsx          # Componente raiz
│   ├── main.tsx         # Ponto de entrada
│   └── index.css        # Estilos globais
├── index.html           # Template HTML
└── vite.config.ts       # Configuração do Vite
```

## Funcionalidades Principais

### Autenticação
- Login com email e senha
- Armazenamento seguro de token JWT no localStorage
- Proteção de rotas privadas
- Logout com limpeza de sessão

### Dashboard
- Visão geral com estatísticas principais
- Cards mostrando total de produtos, alertas ativos, preços competitivos e economia potencial
- Seção de alertas urgentes com ações rápidas
- Integração com API para dados em tempo real

### Gerenciamento de Produtos
- Listagem de produtos monitorados com status
- Informações de preço (seu preço vs preço alvo)
- Contagem de concorrentes por produto
- Botões de ação para visualizar anúncio e concorrentes
- Formulário para adicionar novos produtos
- Validação de formulário com feedback visual

### Alertas
- Listagem de alertas com separação entre lidos e não lidos
- Ações para marcar como lido ou deletar
- Timestamps de criação
- Indicadores visuais de urgência

### Configurações
- Visualização de perfil do usuário
- Opções de segurança e logout
- Espaço para futuras configurações de notificações

## Instalação e Setup

### Pré-requisitos
- Node.js 18+
- pnpm 10+

### Instalação

```bash
# Clonar repositório
git clone <repo-url>
cd frontend-market

# Instalar dependências
pnpm install

# Configurar variáveis de ambiente
cp .env.example .env.local
# Editar .env.local com as URLs corretas
```

### Variáveis de Ambiente

```env
# URL da API do backend
VITE_FRONTEND_FORGE_API_URL=http://localhost:8000

# Configurações da aplicação
VITE_APP_TITLE=MarketAlert
VITE_APP_LOGO=https://seu-logo-url
VITE_APP_ID=seu-app-id
VITE_OAUTH_PORTAL_URL=https://seu-oauth-portal
```

## Desenvolvimento

### Iniciar servidor de desenvolvimento

```bash
pnpm dev
```

O servidor estará disponível em `http://localhost:3000`

### Build para produção

```bash
pnpm build
```

### Verificar tipos TypeScript

```bash
pnpm check
```

### Formatar código

```bash
pnpm format
```

## Integração com Backend

O frontend se comunica com o backend `market_alert` através de uma API REST. As principais rotas utilizadas são:

- `POST /auth` - Autenticação
- `GET /monitored` - Listar produtos monitorados
- `POST /monitored/scrape` - Agendar scraping de produto
- `GET /competitors/{id}` - Listar concorrentes
- `POST /competitors/scrape` - Agendar scraping de concorrente
- `GET /alerts` - Listar alertas
- `POST /alerts/{id}/read` - Marcar alerta como lido
- `DELETE /alerts/{id}` - Deletar alerta
- `POST /comparisons/{id}/run` - Rodar comparação de preços
- `GET /dashboard/stats` - Obter estatísticas do dashboard

## Componentes Principais

### AuthContext
Gerencia o estado de autenticação da aplicação, incluindo token JWT e informações do usuário.

```typescript
const { user, token, isAuthenticated, login, logout } = useAuth();
```

### useMonitoredProducts
Hook para buscar e gerenciar produtos monitorados.

```typescript
const { products, isLoading, error, refetch } = useMonitoredProducts();
```

### useAlerts
Hook para gerenciar alertas do usuário.

```typescript
const { alerts, isLoading, markAsRead, deleteAlert } = useAlerts();
```

### DashboardLayout
Layout padrão para páginas autenticadas com header e navegação.

```typescript
<DashboardLayout>
  <Dashboard />
</DashboardLayout>
```

## Padrões de Código

### Componentes Funcionais com TypeScript
Todos os componentes utilizam TypeScript com tipos bem definidos.

```typescript
interface ComponentProps {
  title: string;
  onClick: () => void;
}

const Component: React.FC<ComponentProps> = ({ title, onClick }) => {
  return <button onClick={onClick}>{title}</button>;
};
```

### Hooks Customizados
Lógica reutilizável é extraída em hooks customizados.

```typescript
export const useCustomLogic = () => {
  const [state, setState] = useState<Type>(initialValue);
  // lógica aqui
  return { state, setState };
};
```

### Tratamento de Erros
Erros são capturados e exibidos ao usuário através de componentes Alert ou Toast.

```typescript
try {
  await apiCall();
} catch (error) {
  setError(error instanceof Error ? error.message : 'Erro desconhecido');
  toast.error('Falha na operação');
}
```

## Responsividade

O frontend é totalmente responsivo, utilizando Tailwind CSS para breakpoints:
- Mobile: < 640px
- Tablet: 640px - 1024px
- Desktop: > 1024px

## Acessibilidade

- Componentes Radix UI com suporte nativo a ARIA
- Navegação por teclado em todos os componentes interativos
- Contraste de cores adequado
- Labels associadas a inputs

## Performance

- Code splitting automático com Vite
- Lazy loading de componentes de página
- Otimização de imagens
- Cache de requisições HTTP

## Próximas Melhorias

- Implementar gráficos de tendência de preços com Recharts
- Adicionar página de visualização de concorrentes
- Implementar filtros e busca avançada
- Adicionar testes unitários e E2E
- Implementar PWA (Progressive Web App)
- Dark mode completo
- Internacionalização (i18n)

## Contribuindo

Para contribuir com o projeto:

1. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
2. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
3. Push para a branch (`git push origin feature/AmazingFeature`)
4. Abra um Pull Request

## Licença

MIT

## Suporte

Para suporte, abra uma issue no repositório ou entre em contato com a equipe de desenvolvimento.
