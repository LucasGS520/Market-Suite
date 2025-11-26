/**
 * Componente de página responsável por exibir a seção de "Alertas e Notificações".
 */

import React from 'react';
import { Box, Typography, Alert } from '@mui/material';
import Layout from '../components/Layout';

/**
 * Componente Alerts
 * Renderiza a página de alertas e notificações do frontend. 
 * Atualmente exibe um cabeçalho descritivo e um Alert informativo indicando que a funcionalidade está em desenvolvimento.
 */
const Alerts: React.FC = () => {
  return (
    // Layout padrão da aplicação (header, nav, footer)
    <Layout>
      {/* Container superior com título e descrição resumida da página */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" gutterBottom>
          Alertas e Notificações
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Histórico de alertas e notificações enviadas
        </Typography>
      </Box>

      {/* Mensagem informativa temporária enquanto a página está em desenvolvimento.
          Substituir por lista de alertas, notificações e controles de gerenciamento quando implementado. */}
      <Alert severity="info">
        Página de alertas em desenvolvimento. Em breve você poderá visualizar e gerenciar seus alertas de preço.
      </Alert>
    </Layout>
  );
};

export default Alerts;
