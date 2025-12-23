/**
 * Componente de apresentação do Dashboard principal da aplicação frontend.
 * 
 * Contém cards de estatísticas resumidas, lista de produtos em destaque e
 * navegação para listas/detalhes de produtos.
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Card,
  CardContent,
  Typography,
  Box,
  CircularProgress,
  Alert,
  Button,
} from '@mui/material';
import Grid from '@mui/material/Grid';
import {
  Inventory as InventoryIcon,
  Notifications as NotificationsIcon,
  CheckCircle as CheckCircleIcon,
  People as PeopleIcon,
  TrendingUp as TrendingUpIcon,
} from '@mui/icons-material';
import { productsService } from '../services/productsService';
import Layout from '../components/Layout';
import TruncatedText from '../utils/TruncatedText';
import ProductStateBadge from '../components/ProductStateBadge';
import { resolveMonitoredStatus } from '../utils/productStatus';
import { renderMonitoredPrice } from '../utils/renderMonitoredPrice';
import type { MonitoredProduct } from '../types';

/**
 * Tipagens locais para maior clareza e manutenção.
 * Ajustar conforme contrato real da API se necessário.
 */
interface DashboardStats {
  total_monitored?: number;
  active_alerts?: number;
  ok_prices?: number;
  total_competitors?: number;
}

/**
 * Componente Dashboard
 *
 * Responsável por:
 * - Buscar estatísticas do dashboard (total de produtos, alertas, etc.)
 * - Buscar produtos em destaque (produtos que requerem atenção)
 * - Renderizar cards de estatísticas e lista de produtos em destaque
 */
const Dashboard: React.FC = () => {
  const navigate = useNavigate();

  // Query para obter estatísticas do dashboard
  const { data: stats, isLoading: statsLoading, error: statsError } = useQuery<DashboardStats>({
    queryKey: ['dashboardStats'],
    queryFn: () => productsService.getDashboardStats(),
  });

  // Query para obter produtos em destaque
  const { data: featuredProducts, isLoading: featuredLoading } = useQuery<MonitoredProduct[]>({
    queryKey: ['featuredProducts'],
    queryFn: () => productsService.getFeaturedProducts(),
  });

  // Estado de carregamento inicial das estatísticas
  if (statsLoading) {
    return (
      <Layout>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <CircularProgress />
        </Box>
      </Layout>
    );
  }

  // Tratamento de erro ao carregar estatísticas
  if (statsError) {
    return (
      <Layout>
        <Alert severity="error">
          Erro ao carregar dados do dashboard. Tente novamente.
        </Alert>
      </Layout>
    );
  }

  // Configuração dos cards de estatísticas exibidos no topo do dashboard
  const statCards = [
    {
      title: 'Produtos Monitorados',
      value: stats?.total_monitored || 0,
      icon: <InventoryIcon fontSize="large" />,
      color: '#1976d2',
    },
    {
      title: 'Alertas Ativos',
      value: stats?.active_alerts || 0,
      icon: <NotificationsIcon fontSize="large" />,
      color: '#ed6c02',
    },
    {
      title: 'Preços Competitivos',
      value: stats?.ok_prices || 0,
      icon: <CheckCircleIcon fontSize="large" />,
      color: '#2e7d32',
    },
    {
      title: 'Total de Concorrentes',
      value: stats?.total_competitors || 0,
      icon: <PeopleIcon fontSize="large" />,
      color: '#9c27b0',
    },
  ];

  return (
    <Layout>
      {/* Cabeçalho do Dashboard */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" gutterBottom>
          Dashboard
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Visão geral do monitoramento de preços
        </Typography>
      </Box>

      {/* Cards de Estatísticas */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        {statCards.map((card, index) => (
          <Grid item xs={12} sm={6} md={3} key={index}>
            <Card elevation={2}>
              <CardContent>
                <Box display="flex" alignItems="center" justifyContent="space-between">
                  <Box>
                    <Typography color="text.secondary" gutterBottom variant="body2">
                      {card.title}
                    </Typography>
                    <Typography variant="h4" component="div">
                      {card.value}
                    </Typography>
                  </Box>
                  {/* Ícone com cor destacada conforme o card */}
                  <Box sx={{ color: card.color }}>
                    {card.icon}
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Seção: Produtos em Destaque */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="h5" gutterBottom>
          Produtos em Destaque
        </Typography>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          Produtos que requerem mais atenção
        </Typography>
      </Box>

      {/* Loader enquanto os produtos em destaque são carregados */}
      {featuredLoading ? (
        <Box display="flex" justifyContent="center" py={4}>
          <CircularProgress />
        </Box>
      ) : featuredProducts && featuredProducts.length > 0 ? (
        <Grid container spacing={3}>
          {featuredProducts.map((product) => {
            const productStatus = resolveMonitoredStatus(product);

            return (
              <Grid item xs={12} md={6} lg={4} key={product.id}>
                <Card
                  elevation={productStatus === 'inactive' ? 0 : 2}
                  sx={{
                    opacity: productStatus === 'inactive' ? 0.75 : 1,
                    backgroundColor: productStatus === 'inactive' ? 'grey.50' : 'background.paper',
                  }}
                >
                  <CardContent>
                    <Box display="flex" gap={2}>
                      {/* Thumbnail do produto (se existir) */}
                      {product.thumbnail && (
                        <Box
                          component="img"
                          src={product.thumbnail}
                          alt={product.name}
                          sx={{
                            width: 80,
                            height: 80,
                            objectFit: 'cover',
                            borderRadius: 1,
                          }}  
                        />
                      )}
                      <Box flex={1}>
                        <TruncatedText text={product.name} variant="h6" lines={2} maxWidth="100%" tooltip={false} />
                        <TruncatedText text={product.url || ''} variant="body2" color="text.secondary" maxWidth="100%" tooltip={true} />
                        <Box display="flex" alignItems="center" gap={1} mt={1}>
                          <ProductStateBadge product={product} />
                          {renderMonitoredPrice(product, { variant: 'h6' })}
                        </Box>
                      </Box>
                    </Box>

                    {/* Botão para navegar aos detalhes do produto */}
                    <Button
                      variant="contained"
                      size="small"
                      fullWidth
                      sx={{ mt: 2 }}
                      onClick={() => navigate(`/product/${product.id}`)}
                      startIcon={<TrendingUpIcon />}
                    >
                      Ver Detalhes
                    </Button>
                  </CardContent>
                </Card>
              </Grid>
            );
          })}
        </Grid>
      ) : (
        // Caso não existam produtos em destaque, informar ao usuário
        <Alert severity="info">
          Nenhum produto em destaque no momento. Adicione produtos para monitorar.
        </Alert>
      )}

      {/* Ações globais, ex.: navegar para lista completa de produtos */}
      <Box sx={{ mt: 4, textAlign: 'center' }}>
        <Button
          variant="outlined"
          color="secondary"
          size="large"
          onClick={() => navigate('/products')}
        >
          Ver Todos os Produtos
        </Button>
      </Box>
    </Layout>
  );
};

export default Dashboard;
