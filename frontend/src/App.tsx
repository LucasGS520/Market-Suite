/**
 * Módulo responsável por orquestrar providers globais e o roteamento principal
 */

import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider, createTheme, CssBaseline } from '@mui/material';
import AuthProvider from './contexts/AuthProvider';
import { ToastProvider } from './contexts/ToastContext';
import ProtectedRoute from './components/ProtectedRoute';

// Páginas
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import Products from './pages/Products';
import ProductDetail from './pages/ProductDetail';
import Compare from './pages/Compare';
import Alerts from './pages/Alerts';
import Settings from './pages/Settings';

/**
 * Cria uma instância do QueryClient do React Query com opções padrão.
 * - refetchOnWindowFocus: desativa refetch ao focar a janela (melhora UX em apps SPA).
 * - retry: tenta 1 vez em caso de falha de rede/servidor.
 * - staleTime: tempo (ms) que os dados são considerados frescos (aqui 5 minutos).
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 5 * 60 * 1000, // 5 minutos
    },
  },
});

/**
 * Tema global do Material-UI (MUI).
 * - Define paleta de cores, tipografia e outras customizações globais.
 * - Ajuste aqui para manter consistência visual em toda a aplicação.
 */
const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#fb8c00', // Laranja - cor primária do sistema
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#fdd835', // Amarelo - cor secundária do sistema
      contrastText: '#000000',
    },
    success: {
      main: '#2e7d32',
    },
    warning: {
      main: '#ed6c02',
    },
    error: {
      main: '#d32f2f',
    },
  },
  typography: {
    fontFamily: 'Inter, system-ui, Avenir, Helvetica, Arial, sans-serif',
  },
});

/**
 * Componente raiz da aplicação.
 * - QueryClientProvider: cache e gerenciamento de requisições com React Query.
 * - ThemeProvider: tema global do MUI.
 * - CssBaseline: reset de estilos base do MUI.
 * - AuthProvider: contexto de autenticação (login/jwt).
 * - BrowserRouter: roteamento do frontend.
 * - ToastProvider: exibição global de toasts (precisa estar dentro do Router).
 *
 * As rotas públicas e protegidas estão declaradas abaixo. Rotas protegidas usam
 * o componente ProtectedRoute que verifica autenticação antes de renderizar.
 */
const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <AuthProvider>
          <BrowserRouter>
            <ToastProvider>
              {/* Mantém o ToastProvider dentro do Router para garantir acesso ao contexto de rota. */}
              <Routes>
                {/* Rotas públicas (acesso sem autenticação) */}
                <Route path="/login" element={<Login />} />
                <Route path="/register" element={<Register />} />

                {/* Rotas protegidas (requerem autenticação) */}
                <Route
                  path="/dashboard"
                  element={
                    <ProtectedRoute>
                      <Dashboard />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/products"
                  element={
                    <ProtectedRoute>
                      <Products />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/product/:id"
                  element={
                    <ProtectedRoute>
                      <ProductDetail />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/compare"
                  element={
                    <ProtectedRoute>
                      <Compare />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/alerts"
                  element={
                    <ProtectedRoute>
                      <Alerts />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/settings"
                  element={
                    <ProtectedRoute>
                      <Settings />
                    </ProtectedRoute>
                  }
                />

                {/* Rota padrão e fallback: redirecionam para o dashboard */}
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
              </Routes>
            </ToastProvider>
          </BrowserRouter>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
};

export default App;
