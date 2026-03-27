/**
 * Componente de página responsável por exibir a seção de "Alertas e Notificações".
 */

import React from 'react';
import { Box, Typography, Alert } from '@mui/material';
import Layout from '../components/Layout';

const Alerts: React.FC = () => {
  return (
    <Layout>
      <Box sx={{ mb: 4 }}>
        <Typography
          variant="h4"
          gutterBottom
          sx={{ fontSize: '1.375rem', fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--color-text-primary)' }}
        >
          Alertas e Notificações
        </Typography>
        <Typography variant="body1" sx={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
          Histórico de alertas e notificações enviadas
        </Typography>
      </Box>

      <Alert
        severity="info"
        sx={{
          backgroundColor: 'var(--color-semantic-info-bg)',
          color: 'var(--color-text-primary)',
          border: '1px solid rgba(59,130,246,0.3)',
          borderLeft: '4px solid var(--color-semantic-info)',
          borderRadius: 'var(--radius-md)',
          '& .MuiAlert-icon': { color: 'var(--color-semantic-info)' },
        }}
      >
        Página de alertas em desenvolvimento. Em breve você poderá visualizar e gerenciar seus alertas de preço.
      </Alert>
    </Layout>
  );
};

export default Alerts;
