/**
 * Página "Comparação de Produtos"
 */

import React from 'react';
import { Box, Typography, Alert } from '@mui/material';
import Layout from '../components/Layout';

const Compare: React.FC = () => {
  return (
    <Layout>
      <Box sx={{ mb: 4 }}>
        <Typography
          variant="h4"
          gutterBottom
          sx={{ fontSize: '1.375rem', fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--color-text-primary)' }}
        >
          Comparação de Produtos
        </Typography>
        <Typography variant="body1" sx={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
          Análise comparativa e competitiva de múltiplos produtos
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
        Página de comparação em desenvolvimento. Em breve você poderá comparar múltiplos produtos lado a lado.
      </Alert>
    </Layout>
  );
};

export default Compare;
