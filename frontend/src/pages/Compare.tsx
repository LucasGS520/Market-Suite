/**
 * Página "Comparação de Produtos"
 */

import React from 'react';
import { Box, Typography, Alert } from '@mui/material';
import Layout from '../components/Layout';

/**
 * Compare
 *
 * Componente funcional (React.FC) que representa a página de comparação.
 * Não recebe props no momento. Futuras iterações devem adicionar props ou
 * hooks para buscar dados do backend e gerenciar seleção de produtos.
 */
const Compare: React.FC = () => {
  return (
    <Layout>
      {/* Cabeçalho da página: título e descrição resumida */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" gutterBottom>
          Comparação de Produtos
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Análise comparativa e competitiva de múltiplos produtos
        </Typography>
      </Box>

      {/* Alerta informativo enquanto a funcionalidade está em desenvolvimento.
          Substituir por componentes de comparação (ex: tabela/grade, seletores)
          quando a implementação estiver pronta. */}
      <Alert severity="info">
        Página de comparação em desenvolvimento. Em breve você poderá comparar múltiplos produtos lado a lado.
      </Alert>
    </Layout>
  );
};

export default Compare;
