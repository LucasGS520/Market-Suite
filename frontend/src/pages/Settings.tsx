/**
 * Página de configurações do usuário do frontend.
 *
 *  Contém seções para exibição de informações do perfil e ações de segurança.
 */

import React from 'react';
import { Box, Typography, Card, CardContent, TextField, Button } from '@mui/material';
import Grid from '@mui/material/Grid';
import { useAuth } from '../hooks/useAuth';
import Layout from '../components/Layout';

/**
 * Componente de página de Configurações do usuário.
 *
 * Exibe informações básicas do perfil (email e nome) e ações relacionadas à segurança.
 * Os campos atuais estão desabilitados (somente leitura). Implementar handlers
 * para editar perfil, alterar senha e verificar email conforme necessidade.
 */
const Settings: React.FC = () => {
  // Recupera informações do usuário a partir do contexto de autenticação
  const { user } = useAuth();

  return (
    // Layout padrão que envolve o conteúdo da página (barra, navegação, etc.)
    <Layout>
      {/* Cabeçalho da página com título e descrição */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" gutterBottom>
          Configurações
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Gerenciamento de dados do usuário e preferências
        </Typography>
      </Box>

      {/* Grid responsivo para organizar cartões de perfil e segurança */}
      <Grid container spacing={3}>
        {/* Cartão com informações do perfil do usuário */}
        <Grid item xs={12} md={6}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Informações do Perfil
              </Typography>

              {/* Campo somente leitura para o email do usuário */}
              <TextField
                fullWidth
                label="Email"
                value={user?.email || ''}
                disabled
                margin="normal"
              />

              {/* Campo somente leitura para o nome do usuário */}
              <TextField
                fullWidth
                label="Nome"
                value={user?.name || ''}
                disabled
                margin="normal"
              />

              {/* Botão placeholder para fluxo de edição de perfil */}
              <Button variant="outlined" sx={{ mt: 2 }}>
                Editar Perfil
              </Button>
            </CardContent>
          </Card>
        </Grid>

        {/* Cartão com ações relacionadas à segurança da conta */}
        <Grid item xs={12} md={6}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Segurança
              </Typography>

              {/* Botão placeholder para fluxo de alteração de senha */}
              <Button variant="outlined" fullWidth sx={{ mt: 2 }}>
                Alterar Senha
              </Button>

              {/* Botão placeholder para fluxo de verificação de email */}
              <Button variant="outlined" fullWidth sx={{ mt: 2 }}>
                Verificar Email
              </Button>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Layout>
  );
};

export default Settings;
