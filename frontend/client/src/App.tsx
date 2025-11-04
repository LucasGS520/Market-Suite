// Ponto de entrada dos componentes de UI e rotas da aplicação frontend.

/* Importações principais de UI, contexto e páginas */
import { Toaster } from "@/components/ui/sonner"; // Componente de notificações (toast)
import { TooltipProvider } from "@/components/ui/tooltip"; // Provedor para tooltips
import NotFound from "@/pages/NotFound";
import { Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary"; // Captura erros em árvore de componentes
import { ThemeProvider } from "./contexts/ThemeContext"; // Contexto de tema (dark/light)
import { AuthProvider } from "./contexts/AuthContext"; // Contexto de autenticação
import { ProtectedRoute } from "./components/ProtectedRoute"; // Protege rotas que exigem login
import { DashboardLayout } from "./components/DashboardLayout"; // Layout comum do dashboard
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Products from "./pages/Products";
import AddProduct from "./pages/AddProduct";
import Competitors from "./pages/Competitors";
import Alerts from "./pages/Alerts";
import Settings from "./pages/Settings";

/* Componente Router:
  - Define as rotas da aplicação usando wouter
  - Rotas que exigem autenticação são aninhadas em ProtectedRoute + DashboardLayout
*/
function Router() {
  return (
   <Switch>
    {/* Rota pública: página de login */}
    <Route path="/login" component={Login} />

    {/* Rota raiz: dashboard principal (protegida) */}
    <Route path="/">
      <ProtectedRoute>
       <DashboardLayout>
        <Dashboard />
       </DashboardLayout>
      </ProtectedRoute>
    </Route>

    {/* Lista de produtos monitorados (protegida) */}
    <Route path="/products">
      <ProtectedRoute>
       <DashboardLayout>
        <Products />
       </DashboardLayout>
      </ProtectedRoute>
    </Route>

    {/* Adicionar novo produto (protegida) */}
    <Route path="/add">
      <ProtectedRoute>
       <DashboardLayout>
        <AddProduct />
       </DashboardLayout>
      </ProtectedRoute>
    </Route>

    {/* Concorrentes de um produto monitorado (protegida)
       - :id corresponde ao ID do produto monitorado */}
    <Route path="/competitors/:id">
      <ProtectedRoute>
       <DashboardLayout>
        <Competitors />
       </DashboardLayout>
      </ProtectedRoute>
    </Route>

    {/* Alertas configurados (protegida) */}
    <Route path="/alerts">
      <ProtectedRoute>
       <DashboardLayout>
        <Alerts />
       </DashboardLayout>
      </ProtectedRoute>
    </Route>

    {/* Configurações do usuário (protegida) */}
    <Route path="/settings">
      <ProtectedRoute>
       <DashboardLayout>
        <Settings />
       </DashboardLayout>
      </ProtectedRoute>
    </Route>

    {/* Rota para página 404 específica */}
    <Route path="/404" component={NotFound} />

    {/* Rota fallback final: qualquer rota não casada cai aqui */}
    <Route component={NotFound} />
   </Switch>
  );
}

/*
NOTA: Sobre Tema
- Primeiro escolha um tema padrão (dark ou light) de acordo com o layout desejado,
  depois ajuste a paleta de cores em index.css para manter coerência entre foreground/background.
- Para permitir mudança de tema em runtime, passe a prop `switchable` para ThemeProvider
  e utilize o hook `useTheme` nos componentes.
*/

function App() {
  return (
   <ErrorBoundary>
    <ThemeProvider
      defaultTheme="light"
      // switchable
    >
      <AuthProvider>
       <TooltipProvider>
        <Toaster />
        <Router />
       </TooltipProvider>
      </AuthProvider>
    </ThemeProvider>
   </ErrorBoundary>
  );
}

export default App;
