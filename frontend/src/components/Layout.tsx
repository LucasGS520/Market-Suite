import React from 'react';
import { Box, Container } from '@mui/material';
import Header from './Header';

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
  return (
    // Box principal que organiza o layout em coluna e garante altura mínima da tela
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {/* Cabeçalho da aplicação */}
      <Header />

      {/* Área principal do conteúdo */}
      <Box component="main" sx={{ flexGrow: 1, py: 3, backgroundColor: 'background.default' }}>
        {/* Container centralizado para limitar a largura do conteúdo e manter responsividade */}
        <Container maxWidth="xl">
          {children}
        </Container>
      </Box>
    </Box>
  );
};

export default Layout;
