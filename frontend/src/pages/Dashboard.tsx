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

interface DashboardStats {
  total_monitored?: number;
  active_alerts?: number;
  ok_prices?: number;
  total_competitors?: number;
}

const Dashboard: React.FC = () => {
  const navigate = useNavigate();

  const { data: stats, isLoading: statsLoading, error: statsError } = useQuery<DashboardStats>({
    queryKey: ['dashboardStats'],
    queryFn: () => productsService.getDashboardStats(),
  });

  const { data: featuredProducts, isLoading: featuredLoading } = useQuery<MonitoredProduct[]>({
    queryKey: ['featuredProducts'],
    queryFn: () => productsService.getFeaturedProducts(),
  });

  // Estado de carregamento: esqueletos no lugar dos cards
  if (statsLoading) {
    return (
      <Layout>
        <Box role="status" aria-label="Carregando dashboard..." sx={{ mb: 4 }}>
          <Box className="skeleton" sx={{ width: 160, height: 32, mb: 1 }} />
          <Box className="skeleton" sx={{ width: 280, height: 20 }} />
        </Box>
        <Grid container spacing={3} sx={{ mb: 4 }}>
          {[0, 1, 2, 3].map((i) => (
            <Grid item xs={12} sm={6} md={3} key={i}>
              <Box className="skeleton" sx={{ height: 100 }} />
            </Grid>
          ))}
        </Grid>
      </Layout>
    );
  }

  if (statsError) {
    return (
      <Layout>
        <Alert
          severity="error"
          sx={{
            backgroundColor: 'var(--color-semantic-danger-bg)',
            color: 'var(--color-text-primary)',
            border: '1px solid rgba(239,68,68,0.3)',
            borderLeft: '4px solid var(--color-semantic-danger)',
            borderRadius: 'var(--radius-md)',
            '& .MuiAlert-icon': { color: 'var(--color-semantic-danger)' },
          }}
        >
          Erro ao carregar dados do dashboard. Tente novamente.
        </Alert>
      </Layout>
    );
  }

  const statCards = [
    {
      title: 'Produtos Monitorados',
      value: stats?.total_monitored || 0,
      icon: <InventoryIcon />,
      color: 'var(--color-accent-primary)',
    },
    {
      title: 'Alertas Ativos',
      value: stats?.active_alerts || 0,
      icon: <NotificationsIcon />,
      color: 'var(--color-semantic-danger)',
    },
    {
      title: 'Preços Competitivos',
      value: stats?.ok_prices || 0,
      icon: <CheckCircleIcon />,
      color: 'var(--color-semantic-success)',
    },
    {
      title: 'Total de Concorrentes',
      value: stats?.total_competitors || 0,
      icon: <PeopleIcon />,
      color: 'var(--color-accent-secondary)',
    },
  ];

  return (
    <Layout>
      <Box sx={{ mb: 4 }}>
        <Typography
          variant="h4"
          gutterBottom
          sx={{ fontSize: '1.375rem', fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--color-text-primary)' }}
        >
          Dashboard
        </Typography>
        <Typography variant="body1" sx={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
          Visão geral do monitoramento de preços
        </Typography>
      </Box>

      <Grid container spacing={3} sx={{ mb: 4 }}>
        {statCards.map((card, index) => (
          <Grid item xs={12} sm={6} md={3} key={index}>
            <Card
              elevation={0}
              className="card-enter"
              style={{ animationDelay: `calc(var(--motion-stagger) * ${index})` }}
              sx={{
                backgroundColor: 'var(--color-surface-card)',
                border: '1px solid var(--color-border-subtle)',
                borderRadius: 'var(--radius-lg)',
                backdropFilter: 'blur(8px)',
                boxShadow: 'var(--shadow-sm)',
                transition: `box-shadow var(--motion-fast) var(--motion-easing), border-color var(--motion-fast) var(--motion-easing)`,
                '&:hover': {
                  boxShadow: 'var(--shadow-md)',
                  borderColor: 'var(--color-border-default)',
                },
              }}
            >
              <CardContent>
                <Box display="flex" alignItems="center" justifyContent="space-between">
                  <Box>
                    <Typography
                      variant="body2"
                      gutterBottom
                      sx={{ color: 'var(--color-text-muted)', fontSize: '0.75rem', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em' }}
                    >
                      {card.title}
                    </Typography>
                    <Typography
                      variant="h4"
                      component="div"
                      sx={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-text-primary)', lineHeight: 1 }}
                    >
                      {card.value}
                    </Typography>
                  </Box>
                  <Box sx={{ color: card.color, opacity: 0.85 }}>
                    {card.icon}
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Box sx={{ mb: 2 }}>
        <Typography
          variant="h5"
          gutterBottom
          sx={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--color-text-primary)' }}
        >
          Produtos em Destaque
        </Typography>
        <Typography variant="body2" sx={{ color: 'var(--color-text-muted)', fontSize: '0.875rem', mb: 2 }}>
          Produtos que requerem mais atenção
        </Typography>
      </Box>

      {featuredLoading ? (
        <Grid container spacing={3} role="status" aria-label="Carregando produtos em destaque...">
          {[0, 1, 2].map((i) => (
            <Grid item xs={12} md={6} lg={4} key={i}>
              <Box className="skeleton" sx={{ height: 160 }} />
            </Grid>
          ))}
        </Grid>
      ) : featuredProducts && featuredProducts.length > 0 ? (
        <Grid container spacing={3}>
          {featuredProducts.map((product) => {
            const productStatus = resolveMonitoredStatus(product);
            const isInactive = productStatus === 'inactive';

            return (
              <Grid item xs={12} md={6} lg={4} key={product.id}>
                <Card
                  elevation={0}
                  className="card-interactive card-enter"
                  onClick={() => navigate(`/product/${product.id}`)}
                  sx={{
                    cursor: 'pointer',
                    backgroundColor: 'var(--color-surface-card)',
                    border: '1px solid var(--color-border-subtle)',
                    borderRadius: 'var(--radius-lg)',
                    backdropFilter: 'blur(8px)',
                    opacity: isInactive ? 0.6 : 1,
                  }}
                >
                  <CardContent>
                    <Box display="flex" gap={2}>
                      {product.thumbnail && (
                        <Box
                          component="img"
                          src={product.thumbnail}
                          alt={product.name}
                          sx={{ width: 80, height: 80, objectFit: 'cover', borderRadius: 'var(--radius-md)', flexShrink: 0 }}
                        />
                      )}
                      <Box flex={1} minWidth={0}>
                        <TruncatedText text={product.name} variant="h6" lines={2} maxWidth="100%" tooltip={false} />
                        <TruncatedText text={product.url || ''} variant="body2" color="text.secondary" maxWidth="100%" tooltip={true} />
                        <Box display="flex" alignItems="center" gap={1} mt={1}>
                          <ProductStateBadge product={product} />
                          {renderMonitoredPrice(product, { variant: 'h6' })}
                        </Box>
                      </Box>
                    </Box>

                    <Button
                      variant="outlined"
                      size="small"
                      fullWidth
                      sx={{
                        mt: 2,
                        color: 'var(--color-accent-primary)',
                        borderColor: 'var(--color-border-accent)',
                        borderRadius: 'var(--radius-md)',
                        fontSize: '0.8125rem',
                        textTransform: 'none',
                        '&:hover': {
                          backgroundColor: 'var(--color-surface-active)',
                          borderColor: 'var(--color-accent-primary)',
                        },
                      }}
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/product/${product.id}`);
                      }}
                      startIcon={<TrendingUpIcon fontSize="small" />}
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
          Nenhum produto em destaque no momento. Adicione produtos para monitorar.
        </Alert>
      )}

      <Box sx={{ mt: 4, textAlign: 'center' }}>
        <Button
          variant="outlined"
          size="large"
          onClick={() => navigate('/products')}
          sx={{
            color: 'var(--color-text-muted)',
            borderColor: 'var(--color-border-default)',
            borderRadius: 'var(--radius-md)',
            textTransform: 'none',
            fontWeight: 500,
            px: 4,
            '&:hover': {
              color: 'var(--color-text-primary)',
              borderColor: 'var(--color-border-accent)',
              backgroundColor: 'var(--color-surface-hover)',
            },
          }}
        >
          Ver Todos os Produtos
        </Button>
      </Box>
    </Layout>
  );
};

export default Dashboard;
