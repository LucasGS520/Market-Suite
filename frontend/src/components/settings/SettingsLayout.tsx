/**
 * Layout padrão da página de configurações
 * Mantém o menu lateral fixo e o painel principal para renderização do conteúdo das seções
 */

import React from 'react';
import { Box, Divider, Stack, Typography } from '@mui/material';
import Layout from '../Layout';

interface SettingsLayoutProps {
    title: string;
    subtitle: string;
    menu: React.ReactNode;
    children: React.ReactNode;
};

/**
 * SettingsLayout
 * Componente responsável por estruturar a página de configurações em duas colunas
 */
const SettingsLayout: React.FC<SettingsLayoutProps> = ({ title, subtitle, menu, children }) => {
  return (
    <Layout>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h4" gutterBottom>
            {title}
          </Typography>
          <Typography variant="body1" color="text.secondary">
            {subtitle}
          </Typography>
        </Box>
        <Divider />
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', md: '280px 1fr' },
            gap: 3,
            alignItems: 'start',
          }}
        >
          <Box>{menu}</Box>
          <Box>{children}</Box>
        </Box>
      </Stack>
    </Layout>
  );
};

export default SettingsLayout;
