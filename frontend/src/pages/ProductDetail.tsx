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
  Tooltip,
} from '@mui/material';
import Grid from '@mui/material/Grid';
import {
  ArrowBack as ArrowBackIcon,
  Add as AddIcon,
  Delete as DeleteIcon,
  Pause as PauseIcon,
  OpenInNew as OpenInNewIcon,
} from '@mui/icons-material';
import { productsService } from '../services/productsService';
import Layout from '../components/Layout';
import { formatCurrency, normalizePriceInput } from '../utils/currency';
import { formatDateOnly, formatDateTime, formatRelativeTime } from '../utils/date';
import TruncatedText from '../utils/TruncatedText';
import MonitoredStateBadge from '../components/MonitoredStateBadge';
import { resolveMonitoredStatus } from '../utils/monitoredStatus';

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
      name: competitorName.trim() || undefined,
    });
  };

  /**
   * Gera um nome amigável a partir do domínio/URL quando não há nome salvo.
   */
  const fallbackFromUrl = (url: string) => {
    try {
      const parsedUrl = new URL(url);
      return parsedUrl.hostname || 'Concorrente';
    } catch {
      return 'Concorrente';
    }
  };

  /**
   * Exibe aviso simples para ações que ainda não foram conectadas ao backend.
   */
  const handlePlaceholderAction = (message: string) => {
    alert(message);
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
   * Define estado do item (monitorado ou concorrente) para guiar rótulos e cores.
   */
  const resolveItemState = (
    value: string | number | null,
    availability?: boolean,
    lastScrapedAt?: string | null,
    isPaused?: boolean,
  ) => {
    const normalized = normalizePriceInput(value);

    if (isPaused) return 'paused' as const;
    if (availability === false) return 'inactive' as const;
    if (availability === true && normalized === null && lastScrapedAt) return 'no_price' as const;
    if (!lastScrapedAt && normalized === null) return 'collecting' as const;
    return normalized !== null ? ('active' as const) : ('unknown' as const);
  };

  /**
   * Renderiza preço do monitorado ou concorrente com fallback de indisponibilidade.
   */
  const renderPrice = (
    value: string | number | null,
    availability?: boolean,
    lastStatus?: string,
    lastScrapedAt?: string | null,
    isPaused?: boolean,
  ) => {
    const normalized = normalizePriceInput(value);
    const state = resolveItemState(value, availability, lastScrapedAt, isPaused);

    if (state === 'paused') {
      return (
        <Typography variant="body2" color="text.secondary">
          Monitoramento pausado
        </Typography>
      );
    }

    if (state === 'inactive') {
      return (
        <Box display="flex" flexDirection="column" gap={0.5}>
          <Typography variant="body2" color="text.secondary">
            Indisponível no site
          </Typography>
          {lastStatus && <Chip label={lastStatus} size="small" color="default" />}
          {lastScrapedAt && (
            <Typography variant="caption" color="text.secondary">
              Última coleta: {formatDateTime(lastScrapedAt)}
            </Typography>
          )}
        </Box>
      );
    }

    if (state === 'no_price') {
      return (
        <Box display="flex" flexDirection="column" gap={0.25}>
          <Typography variant="body2" color="text.secondary">
            Sem preço identificado
          </Typography>
          {lastScrapedAt && (
            <Typography variant="caption" color="text.secondary">
              Coletado em {formatDateOnly(lastScrapedAt)}
            </Typography>
          )}
        </Box>
      );
    }

    if (state === 'collecting') {
      return (
        <Typography variant="body2" color="text.secondary">
          Coletando dados...
        </Typography>
      );
    }

    return formatCurrency(normalized, { fallbackLabel: 'Sem preço' });  
  };

  const renderSummaryCurrency = (value?: string | number | null) => {
    if (value === null || value === undefined || normalizePriceInput(value, { allowZero: true }) === null) {
      return '—';
    }

    return formatCurrency(value, { fallbackLabel: '—', allowZero: true });
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

  const renderDateTime = (value?: string | null) => {
    return formatDateTime(value);
  };

  const resolveAlertLabel = (alert: Record<string, unknown>) => {
    const typedAlert = alert as { message?: string; title?: string; type?: string };
    const message = typedAlert.message || typedAlert.title || typedAlert.type;
    return message || 'Alerta disponível';
  };

  const summaryAlerts = summary?.alerts || [];
  const highlightedAlerts = summaryAlerts.slice(0, 3);
  const monitoredSince = product.created_at;
  const monitoringPaused = product.is_paused ?? false;
  // Usa o timestamp real de scraping por produto, evitando exibir apenas o horário do batch do Beat
  const lastCollectedAt = product.last_scraped_at || product.last_checked || product.created_at;
  const lastPriceChangeAt = product.last_price_change_global_at || product.last_price_change_at;
  const monitoredStatus = resolveMonitoredStatus(product);

  return (
    <Layout>
      {/* Cabeçalho da página com botão de voltar */}
      <Box sx={{ mb: 4 }}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/products')}
          sx={{ mb: 2 }}
          color="secondary"
        >
          Voltar para Produtos
        </Button>
        <Typography variant="h4" gutterBottom>
          Detalhes do Produto
        </Typography>
      </Box>

      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          <Box display="flex" flexDirection="column" gap={3}>
            
            {/* Cartão com informações principais do produto */}
            <Card
              elevation={monitoredStatus === 'inactive' || monitoredStatus === 'paused' ? 0 : 2}
              sx={{
                border: '1px solid',
                borderColor:
                  monitoredStatus === 'inactive' || monitoredStatus === 'paused'
                    ? 'divider'
                    : 'transparent',
                backgroundColor:
                  monitoredStatus === 'inactive' || monitoredStatus === 'paused'
                    ? 'grey.50'
                    : 'background.paper',
                opacity: monitoredStatus === 'inactive' || monitoredStatus === 'paused' ? 0.8 : 1,
              }}
            >
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
                      <Box sx={{ maxWidth: 500 }}>
                        <TruncatedText
                          text={product.name}
                          variant="h5"
                          gutterBottom
                          lines={2}
                          maxWidth={480}
                          tooltip={false}
                        />
                        <TruncatedText
                          text={product.url}
                          variant="body2"
                          color="text.secondary"
                          maxWidth={480}
                          tooltip={true}
                        />
                      </Box>
                      <MonitoredStateBadge product={product} />
                    </Box>

                    <Grid container spacing={2} sx={{ mt: 2 }}>
                      <Grid item xs={12} sm={4}>
                        <Typography variant="body2" color="text.secondary">
                          Preço Atual
                        </Typography>
                        <Typography variant="h4" color="primary">
                          {renderPrice(
                            product.current_price,
                            product.availability,
                            product.last_status,
                            product.last_scraped_at,
                            product.is_paused,
                          )}
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
              <Card elevation={2}>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Resumo de Comparação
                  </Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={12} sm={6} md={4}>
                      <Typography variant="body2" color="text.secondary">
                        Total de Concorrentes
                      </Typography>
                      <Typography variant="h6">{summary.competitors_count ?? 0}</Typography>
                    </Grid>
                    <Grid item xs={12} sm={6} md={4}>
                      <Typography variant="body2" color="text.secondary">
                        Concorrentes com preço
                      </Typography>
                      <Typography variant="h6">{summary.competitors_with_price_count ?? 0}</Typography>
                    </Grid>
                    <Grid item xs={12} sm={6} md={4}>
                      <Typography variant="body2" color="text.secondary">
                        Seu preço (resumo)
                      </Typography>
                      <Typography variant="h6">
                        {renderSummaryCurrency(summary?.monitored_price)}
                      </Typography>
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
                        Preço Mínimo
                      </Typography>
                      <Typography variant="h6">
                        {renderSummaryCurrency(summary?.competitors_min)}
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
                        Reduzir seu Preço
                      </Typography>
                      <Typography
                        variant="h6"
                        color={resolveAdjustmentColor(summary?.potential_adjustment)}
                      >
                        {renderSummaryCurrency(summary?.potential_adjustment)}
                      </Typography>
                    </Grid>
                  </Grid>
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
                          <TableCell sx={{ maxWidth: 420, width: 420 }}>Produto</TableCell>
                          <TableCell align="right" sx={{ width: 160 }}>
                            Preço
                          </TableCell>
                          <TableCell align="center" sx={{ width: 180 }}>
                            Disponibilidade
                          </TableCell>
                          <TableCell align="center" sx={{ width: 140 }}>
                            Status
                          </TableCell>
                          <TableCell align="center" sx={{ width: 160 }}>
                            Ações
                          </TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {competitors.items.map((competitor) => {
                          const resolvedName =
                            competitor.name || competitor.display_name || fallbackFromUrl(competitor.url);
                          const isPendingName = !competitor.name && !competitor.display_name;

                            const nameContent = (
                              <TruncatedText
                                text={resolvedName}
                                variant="body2"
                                lines={2}
                                maxWidth={380}
                                tooltip={false}
                                sx={{ fontStyle: isPendingName ? 'italic' : 'normal' }}
                              />
                            );

                          const wrappedName = isPendingName ? (
                            <Tooltip title="Coletando nome...">{nameContent}</Tooltip>
                          ) : (
                            nameContent
                          );

                          return (
                            <TableRow key={competitor.id}>
                              <TableCell sx={{ maxWidth: 420, width: 420 }}>
                                <Box display="flex" alignItems="center" gap={1}>
                                  {competitor.thumbnail && (
                                    <Box
                                      component="img"
                                      src={competitor.thumbnail}
                                      alt={resolvedName}
                                      sx={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 1 }}
                                    />
                                  )}
                                  <Box sx={{ maxWidth: 380, display: 'flex', flexDirection: 'column', gap: 0.25 }}>
                                    {wrappedName}
                                    <TruncatedText
                                      text={new URL(competitor.url).hostname}
                                      variant="caption"
                                      color="text.secondary"
                                      maxWidth={360}
                                      tooltip={true}
                                    />
                                    {isPendingName && (
                                      <TruncatedText
                                        text="Coletando nome..."
                                        variant="caption"
                                        color="text.secondary"
                                        maxWidth={360}
                                        tooltip={false}
                                      />
                                    )}
                                  </Box>
                                </Box>
                              </TableCell>
                              <TableCell align="right">
                                {renderPrice(
                                  competitor.current_price,
                                  competitor.availability,
                                  competitor.last_status,
                                  competitor.last_scraped_at,
                                  competitor.is_paused,
                                )}
                              </TableCell>
                              <TableCell align="center">
                                <Chip
                                  label={competitor.availability ? 'Disponível' : 'Indisponível'}
                                  color={competitor.availability ? 'success' : 'default'}
                                  size="small"
                                  title={competitor.availability ? 'Disponível no site' : 'Indisponível no site'}
                                />
                              </TableCell>
                              <TableCell align="center">
                                <Chip
                                  label={competitor.is_paused ? 'Pausado' : 'Ativo'}
                                  color={competitor.is_paused ? 'default' : 'success'}
                                  size="small"
                                  title={competitor.is_paused ? 'Monitoramento pausado' : 'Monitoramento ativo'}
                                />
                              </TableCell>
                              <TableCell align="center" sx={{ whiteSpace: 'nowrap' }}>
                                <IconButton
                                  size="small"
                                  color="default"
                                  component="a"
                                  href={competitor.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  aria-label="Ver anúncio do concorrente"
                                >
                                  <OpenInNewIcon />
                                </IconButton>
                                
                                {/* Excluir concorrente: ação não implementada — apresentar feedback claro e estado desabilitado */}
                                <Tooltip title="Remoção de concorrentes não implementada" placement="top">
                                  <span>
                                    <IconButton size="small" color="error" disabled aria-label="Remoção não implementada">
                                      <DeleteIcon />
                                    </IconButton>
                                  </span>
                                </Tooltip>
                              </TableCell>
                            </TableRow>
                          );
                        })}
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
          </Box>
        </Grid>

        <Grid item xs={12} md={4}>
          <Box display="flex" flexDirection="column" gap={3}>
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Insights de Comparação
                </Typography>
                {summary?.comparison_insights ? (
                  <Alert severity="info" sx={{ mb: highlightedAlerts.length ? 2 : 0 }}>
                    {summary.comparison_insights}
                  </Alert>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    Sem Insights disponíveis no momento.
                  </Typography>
                )}

                {highlightedAlerts.length > 0 && (
                  <Box mt={1} display="flex" flexDirection="column" gap={1}>
                    <Typography variant="subtitle2" color="text.secondary">
                      Alertas recentes
                    </Typography>
                    {highlightedAlerts.map((alert, index) => (
                      <Alert key={`alert-${index}`} severity="warning" icon={false} sx={{ py: 0.5 }}>
                        {resolveAlertLabel(alert)}
                      </Alert>
                    ))}
                  </Box>
                )}
              </CardContent>
            </Card>

            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Ações Rápidas
                </Typography>
                <Box display="flex" flexDirection="column" gap={1.5}>
                  <Button
                    variant="contained"
                    startIcon={<AddIcon />}
                    onClick={() => setOpenAddCompetitorDialog(true)}
                  >
                    Adicionar Concorrente
                  </Button>
                  <Button
                    variant="outlined"
                    color="inherit"
                    startIcon={<OpenInNewIcon />}
                    component="a"
                    href={product.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    sx={{
                      color: 'text.primary',
                      borderColor: 'divider',
                      '&:hover': { backgroundColor: 'action.hover' },
                    }}
                  >
                    Ver Anúncio
                  </Button>
                  <Tooltip title="Funcionalidade não implementada — apenas visual por ora" placement="top">
                    <Button
                      variant="outlined"
                      color="warning"
                      startIcon={<PauseIcon />}
                      onClick={() => handlePlaceholderAction('Funcionalidade não implementada: pausar monitoramento ainda não disponível.')}
                    >
                      {monitoringPaused ? 'Ativar Monitoramento' : 'Pausar Monitoramento'}
                    </Button>
                  </Tooltip>
                  <Tooltip title="Remoção de produto não implementada" placement="top">
                    <Button
                      variant="outlined"
                      color="error"
                      startIcon={<DeleteIcon />}
                      onClick={() => handlePlaceholderAction('Funcionalidade não implementada: remoção de produto ainda não disponível.')}
                    >
                      Remover Produto
                    </Button>
                  </Tooltip>
                </Box>
              </CardContent>
            </Card>

            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Estatísticas
                </Typography>
                <Box display="flex" flexDirection="column" gap={1.5}>
                  <Box display="flex" justifyContent="space-between">
                    <Typography variant="body2" color="text.secondary">
                      Última coleta
                    </Typography>
                    <Typography variant="body1">{renderDateTime(lastCollectedAt)}</Typography>
                  </Box>
                  <Box display="flex" justifyContent="space-between">
                    <Typography variant="body2" color="text.secondary">
                      Última mudança de preço
                    </Typography>
                    <Typography variant="body1">
                      {formatRelativeTime(lastPriceChangeAt)}
                    </Typography>
                  </Box>
                  <Box display="flex" justifyContent="space-between">
                    <Typography variant="body2" color="text.secondary">
                      Monitorado desde
                    </Typography>
                    <Typography variant="body1">{formatDateOnly(monitoredSince)}</Typography>
                  </Box>
                  <Box display="flex" justifyContent="space-between">
                    <Typography variant="body2" color="text.secondary">
                      Alertas enviados
                    </Typography>
                    <Typography variant="body1">{product.alerts_sent ?? '—'}</Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Box>
        </Grid>
      </Grid>

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
            margin="dense"
            label="Nome de Identificação (opcional)"
            type="text"
            fullWidth
            value={competitorName}
            onChange={(e) => setCompetitorName(e.target.value)}
            placeholder="Ex: Produto Concorrente"
          />
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
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            O concorrente será adicionado.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenAddCompetitorDialog(false)} color="secondary">
            Cancelar
          </Button>
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
