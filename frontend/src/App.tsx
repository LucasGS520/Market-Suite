/**
 * Módulo responsável por orquestrar providers globais e o roteamento principal
 */

import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider, createTheme, CssBaseline, Box } from '@mui/material';
import AuthProvider from './contexts/AuthProvider';
import { ToastProvider } from './contexts/ToastContext';
import ProtectedRoute from './components/ProtectedRoute';

// Páginas
import Login from './pages/Login';
import Register from './pages/Register';
import VerifyEmail from './pages/VerifyEmail';
import VerifyPhone from './pages/VerifyPhone';
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

const overlayPaperStyles = {
  backgroundImage: 'none',
  border: '1px solid var(--color-border-overlay)',
  boxShadow: 'var(--shadow-overlay)',
  backdropFilter: 'none',
  color: 'var(--color-text-primary)',
};

const modalPaperStyles = {
  ...overlayPaperStyles,
  backgroundColor: 'var(--color-surface-modal)',
};

const contextualPaperStyles = {
  backgroundImage: 'none',
  backgroundColor: 'var(--color-surface-popover)',
  border: '1px solid var(--color-border-contextual)',
  boxShadow: 'var(--shadow-contextual)',
  backdropFilter: 'none',
  color: 'var(--color-text-primary)',
};

const popoverPaperStyles = {
  ...contextualPaperStyles,
  backgroundColor: 'var(--color-surface-popover)',
};

/**
 * Tema global do Material-UI (MUI).
 * - Define paleta de cores, tipografia e outras customizações globais.
 * - Ajuste aqui para manter consistência visual em toda a aplicação.
 */
const theme = createTheme({
  palette: {
    mode: 'dark',
    background: {
      default: '#0a0a0a',
      paper: 'rgba(255, 255, 255, 0.04)',
    },
    primary: {
      main: '#FE7B02',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#FDD835',
      contrastText: '#000000',
    },
    success: {
      main: '#10B981',
    },
    warning: {
      main: '#F59E0B',
    },
    error: {
      main: '#EF4444',
    },
    info: {
      main: '#3B82F6',
    },
    text: {
      primary: '#FFFFFF',
      secondary: '#E4E4E7',
      disabled: '#52525B',
    },
    divider: 'rgba(255, 255, 255, 0.10)',
  },
  typography: {
    fontFamily: "'Inter', system-ui, Avenir, Helvetica, Arial, sans-serif",
  },
  shape: {
    borderRadius: 8,
  },
  components: {
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          backgroundColor: 'rgba(255, 255, 255, 0.04)',
          border: '1px solid rgba(255, 255, 255, 0.05)',
        },
      },
    },
    MuiModal: {
      styleOverrides: {
        root: {
          '& .MuiBackdrop-root': {
            backgroundColor: 'var(--color-overlay-backdrop)',
            backdropFilter: 'blur(4px)',
          },
        },
      },
    },
    MuiBackdrop: {
      styleOverrides: {
        root: {
          backgroundColor: 'var(--color-overlay-backdrop)',
          backdropFilter: 'blur(4px)',
        },
        invisible: {
          backgroundColor: 'transparent',
          backdropFilter: 'none',
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          ...modalPaperStyles,
          borderRadius: 12,
          overflow: 'hidden',
        },
      },
    },
    MuiDialogTitle: {
      styleOverrides: {
        root: {
          padding: '20px 24px 16px',
          backgroundColor: 'transparent',
          borderBottom: '1px solid var(--color-border-overlay)',
        },
      },
    },
    MuiDialogContent: {
      styleOverrides: {
        root: {
          padding: '20px 24px',
          backgroundColor: 'transparent',
          '&:first-of-type': {
            paddingTop: 20,
          },
        },
      },
    },
    MuiDialogActions: {
      styleOverrides: {
        root: {
          padding: '16px 24px 20px',
          backgroundColor: 'transparent',
          borderTop: '1px solid var(--color-border-overlay)',
        },
      },
    },
    MuiPopover: {
      defaultProps: {
        slotProps: {
          backdrop: {
            invisible: true,
          },
        },
      },
      styleOverrides: {
        root: {
          '& .MuiBackdrop-root': {
            backgroundColor: 'transparent',
            backdropFilter: 'none',
          },
        },
        paper: {
          ...popoverPaperStyles,
          borderRadius: 10,
        },
      },
    },
    MuiMenu: {
      styleOverrides: {
        paper: {
          ...popoverPaperStyles,
          borderRadius: 10,
          marginTop: 6,
        },
        list: {
          paddingTop: 2,
          paddingBottom: 2,
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderRadius: 8,
          fontWeight: 500,
        },
        containedPrimary: {
          background: 'var(--color-accent-gradient)',
          color: 'var(--color-text-inverse)',
          boxShadow: '0 0 16px rgba(254, 123, 2, 0.35)',
          '&:hover': {
            background: 'linear-gradient(135deg, #ff8f1a, #ffe45a)',
            boxShadow: '0 0 8px rgba(254, 123, 2, 0.18)',
          },
        },
      },
    },
    MuiInputBase: {
      styleOverrides: {
        root: {
          backgroundColor: 'rgba(255, 255, 255, 0.04)',
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        notchedOutline: {
          borderColor: 'rgba(255, 255, 255, 0.10)',
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: {
          borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
        },
      },
    },
    // Garante anel de foco visível em dark mode (WCAG AA: 3:1 vs #0a0a0a)
    MuiButtonBase: {
      styleOverrides: {
        root: {
          '&.Mui-focusVisible': {
            outline: '2px solid #FE7B02',
            outlineOffset: '2px',
          },
        },
      },
    },
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
        <Box className="app-ambient-background" aria-hidden="true" />
        <Box className="app-shell">
          <AuthProvider>
            <BrowserRouter>
              <ToastProvider>
                {/* Mantém o ToastProvider dentro do Router para garantir acesso ao contexto de rota. */}
                <Routes>
                  {/* Rotas públicas (acesso sem autenticação) */}
                  <Route path="/login" element={<Login />} />
                  <Route path="/register" element={<Register />} />
                  <Route path="/verify-email" element={<VerifyEmail />} />
                  <Route path="/verify-phone" element={<VerifyPhone />} />

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
        </Box>
      </ThemeProvider>
    </QueryClientProvider>
  );
};

export default App;
