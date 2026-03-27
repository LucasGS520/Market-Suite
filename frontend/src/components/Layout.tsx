import React from 'react';
import { Alert, Box, Button, Container, Stack } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import Header from './Header';
import { useAuth } from '../hooks/useAuth';

/**
 * Interface de propriedades do Layout
 * Conteúdo filho que será renderizado dentro do container principal.
 */
interface LayoutProps {
  children: React.ReactNode;
}

/**
 * Componente de layout principal da aplicação.
 *
 * Este componente fornece a estrutura base da página:
 * - Header fixo no topo (importado de ./Header)
 * - Área principal (main) que cresce para preencher a altura disponível
 * - Container centralizado com largura máxima definida para conteúdo
 */
const Layout: React.FC<LayoutProps> = ({ children }) => {
  const { user } = useAuth();
  const shouldShowPendingBanner = 
    !!user &&
    (user.status === 'pending' ||
      !user.email_verified ||
      (!!user.phone_number && !user.phone_number_verified)
    );

  return (
    // Box principal que organiza o layout em coluna e garante altura mínima da tela
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {/* Cabeçalho da aplicação */}
      <Header />

      {/* Área principal do conteúdo */}
      <Box component="main" sx={{ flexGrow: 1, py: 3, backgroundColor: 'transparent' }}>
        {/* Container centralizado para limitar a largura do conteúdo e manter responsividade */}
        <Container maxWidth="xl" className="page-enter">
          {shouldShowPendingBanner && (
            <Alert
              severity="warning"
              sx={{
                mb: 3,
                backgroundColor: 'var(--color-semantic-warning-bg)',
                color: 'var(--color-text-primary)',
                border: '1px solid rgba(245,158,11,0.3)',
                borderLeft: '4px solid var(--color-semantic-warning)',
                borderRadius: 'var(--radius-md)',
                '& .MuiAlert-icon': { color: 'var(--color-semantic-warning)' },
                '& .MuiAlert-action': { color: 'var(--color-text-muted)', alignItems: 'center' },
              }}
              action={
                <Stack direction="row" spacing={1}>
                  <Button
                    size="small"
                    color="inherit"
                    component={RouterLink}
                    to="/verify-email"
                  >
                    Verificar Email
                  </Button>
                  {user.phone_number && (
                    <Button
                      size="small"
                      color="inherit"
                      component={RouterLink}
                      to={`/verify-phone?userId=${user.id}`}
                    >
                      Verificar Telefone
                    </Button>
                  )}
                </Stack>
              }
            >
              Conta pendente - finalize a verificação para utilizar todos os recursos disponíveis.
            </Alert>
          )}
          {children}
        </Container>
      </Box>
    </Box>
  );
};

export default Layout;
