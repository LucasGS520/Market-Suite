/**
 * Componente de página Detalhes do Produto. 
 * 
 * Exibe detalhes de um produto monitorado, resumo de comparação
 * de preços e a lista de concorrentes. Permite adicionar concorrentes.
 */

import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box,
  Typography,
  Button,
  Card,
  CardContent,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  CircularProgress,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  IconButton,
} from '@mui/material';
import Grid from '@mui/material/Grid';
import {
  ArrowBack as ArrowBackIcon,
  Add as AddIcon,
  Delete as DeleteIcon,
  Pause as PauseIcon,
  PlayArrow as PlayArrowIcon,
} from '@mui/icons-material';
import { productsService } from '../services/productsService';
import Layout from '../components/Layout';
import { formatCurrency } from '../utils/currency';

/**
 * Componente de exibição de detalhes do produto monitorado.
 * - Busca os detalhes do produto, concorrentes e um resumo de comparação usando react-query.
 * - Permite adicionar um concorrente.
 */
const ProductDetail: React.FC = () => {
  // Parâmetros da rota (id do produto monitorado)
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Estado local para controlar diálogo de adição de concorrente e campos do formulário
  const [openAddCompetitorDialog, setOpenAddCompetitorDialog] = useState(false);
  const [competitorUrl, setCompetitorUrl] = useState('');
  const [competitorName, setCompetitorName] = useState('');
  const [competitorFeedback, setCompetitorFeedback] = useState<string | null>(null);
  const [competitorError, setCompetitorError] = useState<string | null>(null);

  // Query: detalhes do produto monitorado
  const { data: product, isLoading: productLoading, error: productError } = useQuery({
    queryKey: ['monitoredProduct', id],
    queryFn: () => productsService.getMonitoredProduct(id!),
    enabled: !!id,
  });

  // Query: lista de concorrentes do produto
  const { data: competitors, isLoading: competitorsLoading } = useQuery({
    queryKey: ['competitors', id],
    queryFn: () =>
      productsService.getCompetitors({
        monitored_id: id!,
        page: 1,
        per_page: 100,
      }),
    enabled: !!id,
  });

  // Query: resumo/estatísticas de comparação de preços
  const { data: summary } = useQuery({
    queryKey: ['comparisonSummary', id],
    queryFn: () => productsService.getPriceComparisonSummary(id!),
    enabled: !!id,
  });

  /**
   * Mutation para criar um concorrente.
   * - Ao concluir com sucesso, invalida a query de concorrentes e reseta o diálogo/formulário.
   */
  const createCompetitorMutation = useMutation({
    mutationFn: productsService.createCompetitor,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['competitors', id] });
      setOpenAddCompetitorDialog(false);
      setCompetitorUrl('');
      setCompetitorName('');
      // Mensagem clara para indicar que scraping foi agendado e será atualizado em breve
      setCompetitorFeedback('Concorrente criado e scraping em andamento. Listagem atualizada automaticamente.');
    },
    onError: () => {
      // Orienta o usuário a revisar a URL ou a sessão antes de tentar novamente
      setCompetitorError('Não foi possível adicionar concorrente. Revise a URL e tente novamente')
    }
  });

  /**
   * Handler de adição de concorrente a partir do diálogo.
   * Valida presença de URL e do id do produto antes de disparar a mutation.
   */
  const handleAddCompetitor = () => {
    if (!competitorUrl || !id) return;
    createCompetitorMutation.mutate({
      monitored_product_id: id,
      product_url: competitorUrl,
    });
  };

  // Estado de carregamento do produto: mostra spinner enquanto carrega
  if (productLoading) {
    return (
      <Layout>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <CircularProgress />
        </Box>
      </Layout>
    );
  }

  // Erro ao carregar o produto ou produto inexistente: exibe alerta
  if (productError || !product) {
    return (
      <Layout>
        <Alert severity="error">Erro ao carregar produto. Tente novamente.</Alert>
      </Layout>
    );
  }

  /**
   * Retorna a cor do Chip de status de competitividade com base no status recebido.
   * Status esperados: 'competitivo', 'atencao', 'nao_competitivo', 'urgente'.
   */
  const getStatusColor = (status?: string) => {
    switch (status) {
      case 'competitivo':
        return 'success';
      case 'atencao':
        return 'warning';
      case 'nao_competitivo':
        return 'warning';
      case 'urgente':
        return 'error';
      default:
        return 'default';
    }
  };

  /**
   * Retorna o rótulo legível em PT-BR para o status de competitividade.
   */
  const getStatusLabel = (status?: string) => {
    switch (status) {
      case 'competitivo':
        return 'Competitivo';
      case 'atencao':
        return 'Atenção';
      case 'nao_competitivo':
        return 'Não Competitivo';
      case 'urgente':
        return 'Urgente';
      default:
        return 'Sem Status';
    }
  };

  /**
   * Formata o preço exibindo estado de coleta quando ainda não existe valor salvo
   */
  const renderPrice = (value: string | number | null) => {
    if (value === null) {
      return (
        <Box display="flex" alignItems="center" gap={1}>
          <CircularProgress size={18} />
          <Typography variant="body2" color="text.secondary">
            Scraping em andamento
          </Typography>
        </Box>
      );
    }

    return formatCurrency(value);
  };

  const renderSummaryCurrency = (value?: string | number | null) => {
    if (value === null || value === undefined) {
      return '—';
    }

    return formatCurrency(value, { fallbackLabel: '—' });
  };

  const resolveAdjustmentColor = (value?: string | number | null) => {
    if (value === null || value === undefined) {
      return 'text.primary';
    }

    const adjustmentNumber = Number(value);
    if (Number.isFinite(adjustmentNumber) && adjustmentNumber < 0) {
      return 'success.main';
    }

    return 'error';
  };

  return (
    <Layout>
      {/* Cabeçalho da página com botão de voltar */}
      <Box sx={{ mb: 4 }}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/products')}
          sx={{ mb: 2 }}
        >
          Voltar para Produtos
        </Button>
        <Typography variant="h4" gutterBottom>
          Detalhes do Produto
        </Typography>
      </Box>

      {/* Cartão com informações principais do produto */}
      <Card elevation={2} sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={3}>
            <Grid item xs={12} md={3}>
              {product.thumbnail && (
                <Box
                  component="img"
                  src={product.thumbnail}
                  alt={product.name}
                  sx={{
                    width: '100%',
                    maxWidth: 200,
                    height: 'auto',
                    objectFit: 'cover',
                    borderRadius: 1,
                  }}
                />
              )}
            </Grid>
            <Grid item xs={12} md={9}>
              <Box display="flex" justifyContent="space-between" alignItems="start" mb={2}>
                <Box>
                  <Typography variant="h5" gutterBottom>
                    {product.name}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {product.url}
                  </Typography>
                </Box>
                <Chip
                  label={getStatusLabel(product.competitiveness_status)}
                  color={getStatusColor(product.competitiveness_status)}
                />
              </Box>

              <Grid container spacing={2} sx={{ mt: 2 }}>
                <Grid item xs={12} sm={4}>
                  <Typography variant="body2" color="text.secondary">
                    Preço Atual
                  </Typography>
                  <Typography variant="h4" color="primary">
                    {renderPrice(product.current_price)}
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Typography variant="body2" color="text.secondary">
                    Menor Concorrente
                  </Typography>
                  <Typography variant="h4">
                    {renderSummaryCurrency(summary?.competitors_min)}
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Typography variant="body2" color="text.secondary">
                    Posição no Ranking
                  </Typography>
                  <Typography variant="h4">
                    {summary?.position_rank !== undefined && summary?.position_rank !== null
                      ? `#${summary.position_rank} de ${(summary?.competitors_count || 0) + 1}`
                      : '—'}
                  </Typography>
                </Grid>
              </Grid>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Cartão com resumo de comparação (quando disponível) */}
      {summary && (
        <Card elevation={2} sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Resumo de Comparação
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="body2" color="text.secondary">
                  Total de Concorrentes
                </Typography>
                <Typography variant="h6">{summary.competitors_count}</Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="body2" color="text.secondary">
                  Preço Médio
                </Typography>
                <Typography variant="h6">
                  {renderSummaryCurrency(summary?.competitors_mean)}
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="body2" color="text.secondary">
                  Preço Máximo
                </Typography>
                <Typography variant="h6">
                  {renderSummaryCurrency(summary?.competitors_max)}
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="body2" color="text.secondary">
                  Ajuste Potencial
                </Typography>
                <Typography
                  variant="h6"
                  color={resolveAdjustmentColor(summary?.potential_adjustment)}
                >
                  {renderSummaryCurrency(summary?.potential_adjustment)}
                </Typography>
              </Grid>
            </Grid>
            {summary.comparison_insights && (
              <Alert severity="info" sx={{ mt: 2 }}>
                {summary.comparison_insights}
              </Alert>
            )}
          </CardContent>
        </Card>
      )}

      {/* Cartão com lista de concorrentes e ações */}
      <Card elevation={2}>
        <CardContent>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
            <Typography variant="h6">Concorrentes</Typography>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => setOpenAddCompetitorDialog(true)}
            >
              Adicionar Concorrente
            </Button>
          </Box>

          {/* Feedback para usuário sobre concorrentes */}
          {competitorFeedback && (
            <Alert severity="info" sx={{ mb: 2 }}>
              {competitorFeedback}
            </Alert>
          )}
          {competitorError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {competitorError}
            </Alert>
          )}

          {competitorsLoading ? (
            // Spinner enquanto carrega a lista de concorrentes
            <Box display="flex" justifyContent="center" py={4}>
              <CircularProgress />
            </Box>
          ) : competitors && competitors.items.length > 0 ? (
            // Tabela de concorrentes quando houver itens
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Produto</TableCell>
                    <TableCell align="right">Preço</TableCell>
                    <TableCell align="center">Disponibilidade</TableCell>
                    <TableCell align="center">Status</TableCell>
                    <TableCell align="center">Ações</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {competitors.items.map((competitor) => (
                    <TableRow key={competitor.id}>
                      <TableCell>
                        <Box display="flex" alignItems="center" gap={1}>
                          {competitor.thumbnail && (
                            <Box
                              component="img"
                              src={competitor.thumbnail}
                              alt={competitor.name}
                              sx={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 1 }}
                            />
                          )}
                          <Box>
                            <Typography variant="body2">{competitor.name}</Typography>
                            <Typography variant="caption" color="text.secondary">
                              {new URL(competitor.url).hostname}
                            </Typography>
                          </Box>
                        </Box>
                      </TableCell>
                      <TableCell align="right">
                        {renderPrice(competitor.current_price)}
                      </TableCell>
                      <TableCell align="center">
                        <Chip
                          label={competitor.availability ? 'Disponível' : 'Indisponível'}
                          color={competitor.availability ? 'success' : 'default'}
                          size="small"
                        />
                      </TableCell>
                      <TableCell align="center">
                        <Chip
                          label={competitor.is_paused ? 'Pausado' : 'Ativo'}
                          color={competitor.is_paused ? 'default' : 'success'}
                          size="small"
                        />
                      </TableCell>
                      <TableCell align="center">
                        {/* Ações não implementadas: apenas botões visuais por ora */}
                        <IconButton size="small" color={competitor.is_paused ? 'success' : 'warning'}>
                          {competitor.is_paused ? <PlayArrowIcon /> : <PauseIcon />}
                        </IconButton>
                        <IconButton size="small" color="error">
                          <DeleteIcon />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          ) : (
            // Mensagem quando não há concorrentes cadastrados
            <Alert severity="info">
              Nenhum concorrente cadastrado. Adicione concorrentes para comparar preços.
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Dialog para adicionar novo concorrente */}
      <Dialog
        open={openAddCompetitorDialog}
        onClose={() => setOpenAddCompetitorDialog(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Adicionar Concorrente</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            Adicionar concorrente para: <strong>{product.name}</strong>
          </Alert>
          <TextField
            autoFocus
            margin="dense"
            label="URL do Concorrente"
            type="url"
            fullWidth
            required
            value={competitorUrl}
            onChange={(e) => setCompetitorUrl(e.target.value)}
            placeholder="https://exemplo.com/produto-concorrente"
          />
          <TextField
            margin="dense"
            label="Nome de Identificação (opcional)"
            type="text"
            fullWidth
            value={competitorName}
            onChange={(e) => setCompetitorName(e.target.value)}
            placeholder="Ex: Concorrente A"
          />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            O concorrente será adicionado.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenAddCompetitorDialog(false)}>Cancelar</Button>
          <Button
            onClick={handleAddCompetitor}
            variant="contained"
            disabled={!competitorUrl || createCompetitorMutation.isPending}
          >
            {createCompetitorMutation.isPending ? <CircularProgress size={24} /> : 'Adicionar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Layout>
  );
};

export default ProductDetail;
