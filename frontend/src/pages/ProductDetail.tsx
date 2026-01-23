/**
 * Componente de página Detalhes do Produto. 
 * 
 * Exibe detalhes de um produto monitorado, resumo de comparação
 * de preços e a lista de concorrentes. Permite adicionar concorrentes.
 */

import React, { useEffect, useRef, useState } from 'react';
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
import ProductStateBadge from '../components/ProductStateBadge';
import { resolveMonitoredStatus } from '../utils/productStatus';
import { renderMonitoredPrice } from '../utils/renderMonitoredPrice';
import { CompetitorProduct, MonitoredProduct } from '../types';
import { useToast } from '../hooks/useToast';

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
  const { showToast, dismissToast } = useToast();

  // Estado local para controlar diálogo de adição de concorrente e campos do formulário
  const [openAddCompetitorDialog, setOpenAddCompetitorDialog] = useState(false);
  const [competitorUrl, setCompetitorUrl] = useState('');
  const [competitorName, setCompetitorName] = useState('');
  const [competitorToDelete, setCompetitorToDelete] = useState<CompetitorProduct | null>(null);
  const [confirmCompetitorDeleteOpen, setConfirmCompetitorDeleteOpen] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteButtonRef = useRef<HTMLButtonElement | null>(null);
  const confirmDeleteButtonRef = useRef<HTMLButtonElement | null>(null);


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
        include_inactive: true,
        include_paused: true,
      }),
    enabled: !!id,
  });

  // Query: resumo/estatísticas de comparação de preços
  const { data: summary } = useQuery({
    queryKey: ['comparisonSummary', id],
    queryFn: () => productsService.getPriceComparisonSummary(id!),
    enabled: !!id,
  });

  useEffect(() => {
    if (productError || (!productLoading && !product)) {
      showToast({
        key: `monitoring:product:${id ?? 'unknown'}:load-error`,
        message: 'Erro ao carregar produto. Tente novamente.',
        severity: 'error',
        persist: true,
        replace: true,
      });
    } else if (id) {
      dismissToast(`monitoring:product:${id}:load-error`);
    }
  }, [dismissToast, id, product, productError, productLoading, showToast]);

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
      showToast({
        key: `monitoring:product:${id}:competitor:create`,
        message: 'Concorrente criado e scraping em andamento. A listagem será atualizada automaticamente.',
        severity: 'info',
        replace: true,
      });
    },
    onError: () => {
      // Orienta o usuário a revisar a URL ou a sessão antes de tentar novamente
      showToast({
        key: `monitoring:product:${id}:competitor:create:error`,
        message: 'Não foi possível adicionar concorrente. Revise a URL e tente novamente.',
        severity: 'error',
        persist: true,
        replace: true,
      });
    },
  });

  const deleteCompetitorMutation = useMutation({
    mutationFn: (competitorId: string) => productsService.deleteCompetitor(competitorId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['competitors', id] });
      queryClient.invalidateQueries({ queryKey: ['comparisonSummary', id] });
      setConfirmCompetitorDeleteOpen(false);
      setCompetitorToDelete(null);
      showToast({
        key: `monitoring:product:${id}:competitor:delete`,
        message: 'Concorrente removido. Resumo será recalculado em instantes.',
        severity: 'success',
        replace: true,
      });
    },
    onError: () => {
      showToast({
        key: `monitoring:product:${id}:competitor:delete:error`,
        message: 'Falha ao remover concorrente. Tente novamente.',
        severity: 'error',
        persist: true,
        replace: true,
      });
    },
  });

  /**
   * Mutations de pausa e retomada com atualização otimista na cache do produto.
   */
  const pauseMonitoredMutation = useMutation({
    mutationFn: () => productsService.pauseMonitored(id!),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ['monitoredProduct', id] });
      const previous = queryClient.getQueryData<MonitoredProduct | undefined>(['monitoredProduct', id]);
      const pausedAt = new Date().toISOString();
      const optimistic: MonitoredProduct | undefined = previous
        ? {
            ...previous,
            paused: true,
            is_paused: true,
            paused_at: pausedAt,
            display_status: 'paused',
          }
        : previous;
      if (optimistic) {
        queryClient.setQueryData(['monitoredProduct', id], optimistic);
      }
      return { previous };
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['monitoredProduct', id], data);
      queryClient.invalidateQueries({ queryKey: ['monitoredProduct', id] });
      queryClient.invalidateQueries({ queryKey: ['monitoredProducts'] });
      showToast({
        key: `monitoring:product:${id}:pause`,
        message: 'Monitoramento pausado com sucesso.',
        severity: 'success',
        replace: true,
      });
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['monitoredProduct', id], context.previous);
      }
      showToast({
        key: `monitoring:product:${id}:pause:error`,
        message: 'Não foi possível pausar o monitoramento. Tente novamente.',
        severity: 'error',
        persist: true,
        replace: true,
      });
    },
  });

  const resumeMonitoredMutation = useMutation({
    mutationFn: () => productsService.resumeMonitored(id!),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ['monitoredProduct', id] });
      const previous = queryClient.getQueryData<MonitoredProduct | undefined>(['monitoredProduct', id]);
      const optimistic: MonitoredProduct | undefined = previous
        ? {
            ...previous,
            paused: false,
            is_paused: false,
            paused_at: null,
            display_status: previous.display_status === 'paused' ? 'unknown' : previous.display_status,
          }
        : previous;
      if (optimistic) {
        queryClient.setQueryData(['monitoredProduct', id], optimistic);
      }
      return { previous };
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['monitoredProduct', id], data);
      queryClient.invalidateQueries({ queryKey: ['monitoredProduct', id] });
      queryClient.invalidateQueries({ queryKey: ['monitoredProducts'] });
      showToast({
        key: `monitoring:product:${id}:resume`,
        message: 'Monitoramento retomado. Nova coleta será agendada.',
        severity: 'success',
        replace: true,
      });
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['monitoredProduct', id], context.previous);
      }
      showToast({
        key: `monitoring:product:${id}:resume:error`,
        message: 'Não foi possível retomar o monitoramento. Tente novamente.',
        severity: 'error',
        persist: true,
        replace: true,
      });
    },
  });

  const deleteMonitoredMutation = useMutation({
    mutationFn: () => productsService.deleteProduct(id!),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ['monitoredProduct', id] });
      queryClient.invalidateQueries({ queryKey: ['monitoredProducts'] });
      queryClient.invalidateQueries({ queryKey: ['monitoredProducts', '__all__'] });
      setConfirmDeleteOpen(false);
      showToast({
        key: `monitoring:product:${id}:delete`,
        message: 'Produto removido com sucesso. Histórico e concorrentes foram descartados.',
        severity: 'success',
        replace: true,
      });
      navigate('/products');
    },
    onError: () => {
      // Mantém o modal aberto para permitir nova tentativa e indica falha de forma visível.
      setDeleteError('Falha ao remover produto. Verifique sua conexão e tente novamente.');
      showToast({
        key: `monitoring:product:${id}:delete:error`,
        message: 'Falha ao remover produto. Verifique sua conexão e tente novamente.',
        severity: 'error',
        persist: true,
        replace: true,
      });
    },
  });

  /**
   * Handler de adição de concorrente a partir do diálogo.
   * Valida presença de URL e do id do produto antes de disparar a mutation.
   */
  const handleAddCompetitor = () => {
    if (!competitorUrl || !id) return;
    if (product?.paused ?? product?.is_paused) return;
    createCompetitorMutation.mutate({
      monitored_product_id: id,
      product_url: competitorUrl,
      name: competitorName.trim() || undefined,
    });
  };

  /**
   * Abre modal de remoção de concorrente com o item selecionado.
   */
  const handleOpenCompetitorDelete = (competitor: CompetitorProduct) => {
    setCompetitorToDelete(competitor);
    setConfirmCompetitorDeleteOpen(true);
  };

  /**
   * Confirma remoção do concorrente selecionado.
   */
  const handleConfirmCompetitorDelete = () => {
    if (!competitorToDelete) return;
    if (product?.paused ?? product?.is_paused) return;
    deleteCompetitorMutation.mutate(competitorToDelete.id);
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
   * Alterna monitoramento aplicando pause/resume com atualização otimista.
   */
  const handleToggleMonitoring = () => {
    if (!id) return;
    if (product?.paused ?? product?.is_paused) {
      resumeMonitoredMutation.mutate();
    } else {
      pauseMonitoredMutation.mutate();
    }
  };

  /**
   * Dispara remoção após confirmação explícita.
   */
  const handleDeleteProduct = () => {
    if (!id) return;
    setDeleteError(null);
    deleteMonitoredMutation.mutate();
  };

  // Gerencia foco e acessibilidade do modal de remoção, direcionando foco ao confirmar e devolvendo ao gatilho.
  useEffect(() => {
    if (confirmDeleteOpen) {
      setDeleteError(null);
      confirmDeleteButtonRef.current?.focus();
    } else {
      deleteButtonRef.current?.focus();
    }
  }, [confirmDeleteOpen]);

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
        <Typography color="error">Erro ao carregar produto. Tente novamente.</Typography>
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

    // Mostrar apenas texto compacto na coluna de preço: valor ou um rótulo curto.
    if (state === 'paused') {
      return (
        <Typography variant="body2" color="text.secondary">
          Monitoramento pausado
        </Typography>
      );
    }

    if (state === 'inactive') {
      return (
        <Typography variant="body2" color="text.secondary">
          Indisponível
        </Typography>
      );
    }

    if (state === 'no_price') {
      return (
        <Typography variant="body2" color="text.secondary">
          Sem preço
        </Typography>
      );
    }

    if (state === 'collecting') {
      return (
        <Typography variant="body2" color="text.secondary">
          Coletando dados...
        </Typography>
      );
    }

    return (
      <Typography variant="body1" color="text.primary">
        {formatCurrency(normalized, { fallbackLabel: 'Sem preço' })}
      </Typography>
    );
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
  const monitoringPaused = (product.paused ?? product.is_paused) ?? false;
  const monitoredStatus = resolveMonitoredStatus(product);
  const detailCardOpacity = monitoringPaused ? 0.5 : monitoredStatus === 'inactive' ? 0.8 : 1;
  const competitorActionsBlocked = monitoringPaused;
  // Usa o timestamp real de scraping por produto, evitando exibir apenas o horário do batch do Beat
  const lastCollectedAt = product.last_scraped_at;
  const lastPriceChangeAt = product.last_price_change_global_at || product.last_price_change_at;
  const alertsCount = 
    typeof summary?.alerts_count === 'number'
      ? summary.alerts_count
      : summaryAlerts.length > 0
        ? summaryAlerts.length
        : product.alerts_sent ?? null;
  const actionBusy = pauseMonitoredMutation.isPending || resumeMonitoredMutation.isPending || deleteMonitoredMutation.isPending;

  /**
   * Resolve rótulo de estabilidade para a UI, mantendo consistência com o backend.
   */
  const resolveStabilityLabel = (stability?: MonitoredProduct['stability']): string => {
    const stabilityMap: Record<NonNullable<MonitoredProduct['stability']>, string> = {
      unstable: 'Instável',
      stable: 'Estável',
      very_stable: 'Muito Estável',
    };

    if (!stability) {
      return '—';
    }

    return stabilityMap[stability] ?? '—';
  };

  /**
   * Exibe o tempo relativo da última mudança de preço com fallback seguro
   */
  const renderLastPriceChange = (): string => {
    const relativeLabel = formatRelativeTime(lastPriceChangeAt);
    if (!relativeLabel || relativeLabel === '—') {
      return '—';
    }

    return relativeLabel;
  };

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
              elevation={monitoredStatus === 'inactive' ? 0 : 2}
              sx={{
                border: '1px solid',
                borderColor: monitoringPaused
                  ? 'warning.light'
                  : monitoredStatus === 'inactive'
                    ? 'divider'
                    : 'transparent',
                backgroundColor:
                  monitoringPaused || monitoredStatus === 'inactive' ? 'background.default' : 'background.paper',
                opacity: detailCardOpacity,
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
                      <ProductStateBadge product={product} />
                    </Box>

                    <Grid container spacing={2} sx={{ mt: 2 }}>
                      <Grid item xs={12} sm={4}>
                        <Typography variant="body2" color="text.secondary">
                          Preço Atual
                        </Typography>
                        { /* Padroniza renderização de preço com componente utilitário */ }
                        <Box>
                          {renderMonitoredPrice(product, { variant: 'h4' })}
                        </Box>
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
                        Preço Médio
                      </Typography>
                      <Typography variant="h6">
                        {renderSummaryCurrency(summary?.competitors_mean)}
                      </Typography>
                    </Grid>
                    <Grid item xs={12} sm={6} md={4}>
                      <Typography variant="body2" color="text.secondary">
                        Preço Mínimo
                      </Typography>
                      <Typography variant="h6">
                        {renderSummaryCurrency(summary?.competitors_min)}
                      </Typography>
                    </Grid>
                    <Grid item xs={12} sm={6} md={4}>
                      <Typography variant="body2" color="text.secondary">
                        Preço Máximo
                      </Typography>
                      <Typography variant="h6">
                        {renderSummaryCurrency(summary?.competitors_max)}
                      </Typography>
                    </Grid>
                    <Grid item xs={12} sm={6} md={4}>
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
                  {/* Mostrar botão sem tooltip quando desabilitado; quando habilitado mantém comportamento simples */}
                  {competitorActionsBlocked ? (
                    <Button
                      variant="contained"
                      startIcon={<AddIcon />}
                      onClick={() => setOpenAddCompetitorDialog(true)}
                      disabled
                    >
                      Adicionar Concorrente
                    </Button>
                  ) : (
                    <Button
                      variant="contained"
                      startIcon={<AddIcon />}
                      onClick={() => setOpenAddCompetitorDialog(true)}
                    >
                      Adicionar Concorrente
                    </Button>
                  )}
                </Box>

                {competitorActionsBlocked && (
                  <Alert severity="warning" sx={{ mb: 2 }}>
                    Monitoramento pausado: ações de concorrentes (adição e remoção) estão bloqueadas.
                  </Alert>
                )}

                {competitors && (
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    {`${competitors.competitors_with_price_count} de ${competitors.competitors_total} concorrentes serão considerados nas comparações.`}
                    {competitors.excluded_due_to_inactive_count > 0 && (
                      <>
                        {` (${competitors.excluded_due_to_inactive_count} ignorados por indisponibilidade ou falta de preço).`}
                      </>
                    )}
                  </Typography>
                )}

                {competitorsLoading ? (
                  // Spinner enquanto carrega a lista de concorrentes
                  <Box display="flex" justifyContent="center" py={4}>
                    <CircularProgress />
                  </Box>
                ) : competitors && competitors.items.length > 0 ? (
                  // Tabela de concorrentes quando houver itens
                  <TableContainer>
                    <Table sx={{ tableLayout: 'fixed' }}>
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

                          const excludedFromMetrics =
                            competitor.availability === false || competitor.current_price === null;
                          const availabilityLabel =
                            competitor.availability === false
                              ? 'Indisponível'
                              : competitor.availability === true
                                ? 'Disponível'
                                : 'Aguardando coleta';
                          const availabilityColor =
                            competitor.availability === false
                              ? 'default'
                              : competitor.availability === true
                                ? 'success'
                                : 'warning';

                          
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
                            <TableRow
                              key={competitor.id}
                              sx={{
                                opacity: excludedFromMetrics ? 0.6 : 1,
                                borderLeft: excludedFromMetrics ? '4px solid' : undefined,
                                borderColor: excludedFromMetrics ? 'divider' : undefined,
                                '&:hover': excludedFromMetrics
                                  ? { backgroundColor: 'action.hover' }
                                  : undefined,
                              }}
                            >
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
                              <TableCell align="right" sx={{ verticalAlign: 'middle', width: 160 }}>
                                {renderPrice(
                                  competitor.current_price,
                                  competitor.availability,
                                  competitor.last_status,
                                  competitor.last_scraped_at,
                                  competitor.is_paused,
                                )}
                              </TableCell>
                              <TableCell align="center" sx={{ verticalAlign: 'middle' }}>
                                <Box display="flex" justifyContent="center">
                                  <Chip
                                    label={availabilityLabel}
                                    color={availabilityColor}
                                    size="small"
                                    title={availabilityLabel}
                                  />
                                </Box>
                              </TableCell>
                              <TableCell align="center" sx={{ verticalAlign: 'middle' }}>
                                <Box display="flex" justifyContent="center">
                                  <Chip
                                    label={competitor.is_paused ? 'Pausado' : 'Ativo'}
                                    color={competitor.is_paused ? 'default' : 'success'}
                                    size="small"
                                    title={competitor.is_paused ? 'Monitoramento pausado' : 'Monitoramento ativo'}
                                  />
                                </Box>
                              </TableCell>
                              <TableCell align="center" sx={{ whiteSpace: 'nowrap', verticalAlign: 'middle' }}>
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
                                
                                {/* Mostrar tooltip apenas quando ações não estiverem bloqueadas */}
                                {!competitorActionsBlocked ? (
                                  <Tooltip title="Remover concorrente" placement="top">
                                    <span>
                                      <IconButton
                                        size="small"
                                        color="error"
                                        aria-label="Remover concorrente"
                                        onClick={() => handleOpenCompetitorDelete(competitor)}
                                        disabled={
                                          deleteCompetitorMutation.isPending &&
                                          competitorToDelete?.id === competitor.id
                                        }
                                      >
                                        {deleteCompetitorMutation.isPending && competitorToDelete?.id === competitor.id ? (
                                          <CircularProgress size={18} />
                                        ) : (
                                          <DeleteIcon />
                                        )}
                                      </IconButton>
                                    </span>
                                  </Tooltip>
                                ) : (
                                  <IconButton
                                    size="small"
                                    color="error"
                                    aria-label="Remover concorrente"
                                    onClick={() => handleOpenCompetitorDelete(competitor)}
                                    disabled={
                                      competitorActionsBlocked ||
                                      (deleteCompetitorMutation.isPending && competitorToDelete?.id === competitor.id)
                                    }
                                  >
                                    {deleteCompetitorMutation.isPending && competitorToDelete?.id === competitor.id ? (
                                      <CircularProgress size={18} />
                                    ) : (
                                      <DeleteIcon />
                                    )}
                                  </IconButton>
                                )}
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
                {/** Quando o produto está inativo, deixar explícito que não há comparação válida */}
                {monitoredStatus === 'inactive' || summary?.ignored_due_to_inactive ? (
                  <Alert severity="info" sx={{ mb: highlightedAlerts.length ? 2 : 0 }}>
                    Comparação não realizada: anúncio indisponível no site de origem.
                  </Alert>
                ) : summary?.comparison_insights ? (
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
                  {/* Botão com mesmo estilo dos demais no bloco Ações Rápidas. Sem tooltip quando desabilitado. */}
                  {competitorActionsBlocked ? (
                    <Button
                      variant="contained"
                      startIcon={<AddIcon />}
                      onClick={() => setOpenAddCompetitorDialog(true)}
                      disabled
                      sx={{ alignSelf: 'stretch' }}
                    >
                      Adicionar Concorrente
                    </Button>
                  ) : (
                    <Button
                      variant="contained"
                      startIcon={<AddIcon />}
                      onClick={() => setOpenAddCompetitorDialog(true)}
                      sx={{ alignSelf: 'stretch' }}
                    >
                      Adicionar Concorrente
                    </Button>
                  )}
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
                  <Button
                    variant="outlined"
                    color={monitoringPaused ? 'success' : 'warning'}
                    startIcon={<PauseIcon />}
                    onClick={handleToggleMonitoring}
                    disabled={actionBusy}
                  >
                    {pauseMonitoredMutation.isPending || resumeMonitoredMutation.isPending ? (
                      <CircularProgress size={20} />
                    ) : monitoringPaused ? (
                      'Retomar Monitoramento'
                    ) : (
                      'Pausar Monitoramento'
                    )}
                  </Button>
                  <Button
                    variant="outlined"
                    color="error"
                    startIcon={<DeleteIcon />}
                    onClick={() => {
                      setConfirmDeleteOpen(true);
                    }}
                    disabled={actionBusy}
                    ref={deleteButtonRef}
                  >
                    {deleteMonitoredMutation.isPending ? <CircularProgress size={20} /> : 'Remover Produto'}
                  </Button>
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
                    <Typography variant="body1">{renderLastPriceChange()}</Typography>
                  </Box>
                  <Box display="flex" justifyContent="space-between">
                    <Typography variant="body2" color="text.secondary">
                      Monitorado desde
                    </Typography>
                    <Typography variant="body1">{formatDateOnly(monitoredSince)}</Typography>
                  </Box>
                  <Box display="flex" justifyContent="space-between">
                    <Typography variant="body2" color="text.secondary">
                      Status
                    </Typography>
                    <Typography variant="body1">{resolveStabilityLabel(product.stability)}</Typography>
                  </Box>
                  <Box display="flex" justifyContent="space-between">
                    <Typography variant="body2" color="text.secondary">
                      Alertas enviados
                    </Typography>
                    <Typography variant="body1">{alertsCount ?? '—'}</Typography>
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
        {competitorActionsBlocked && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Monitoramento pausado: retome o produto para cadastrar concorrentes.
          </Alert>
        )}
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
            disabled={!competitorUrl || createCompetitorMutation.isPending || competitorActionsBlocked}
          >
          {createCompetitorMutation.isPending ? <CircularProgress size={24} /> : 'Adicionar'}
        </Button>
      </DialogActions>
    </Dialog>

      {/* Diálogo de confirmação para remover concorrente */}
      <Dialog
        open={confirmCompetitorDeleteOpen}
        onClose={() => setConfirmCompetitorDeleteOpen(false)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Remover concorrente</DialogTitle>
      <DialogContent>
        <Alert severity="warning" sx={{ mb: 2 }}>
          {`Esta ação remove o concorrente ${competitorToDelete?.name || competitorToDelete?.display_name || 'selecionado'} e seu histórico.`}
        </Alert>
        {competitorActionsBlocked && (
          <Alert severity="info" sx={{ mb: 2 }}>
            Monitoramento pausado: retome o produto para remover concorrentes.
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button
          onClick={() => setConfirmCompetitorDeleteOpen(false)}
          color="secondary"
          disabled={deleteCompetitorMutation.isPending}
        >
          Cancelar
        </Button>
        <Button
          onClick={handleConfirmCompetitorDelete}
          variant="contained"
          color="error"
          disabled={deleteCompetitorMutation.isPending || competitorActionsBlocked}
        >
            {deleteCompetitorMutation.isPending ? <CircularProgress size={24} /> : 'Remover'}  
          </Button>
        </DialogActions>
      </Dialog>

      {/* Diálogo de confirmação para remover monitorado */}
      <Dialog
        open={confirmDeleteOpen}
        onClose={() => setConfirmDeleteOpen(false)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Remover produto monitorado</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            Esta ação remove o monitorado, histórico de preços e concorrentes de forma definitiva. Deseja continuar?
          </Alert>
          {deleteError && (
            <Alert severity="error" sx={{ mb: 1 }}>
              {deleteError}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDeleteOpen(false)} color="secondary" disabled={deleteMonitoredMutation.isPending}>
            Cancelar
          </Button>
          <Button
            onClick={handleDeleteProduct}
            variant="contained"
            color="error"
            disabled={deleteMonitoredMutation.isPending}
            ref={confirmDeleteButtonRef}
          >
            {deleteMonitoredMutation.isPending ? <CircularProgress size={24} /> : 'Remover'}
          </Button>
        </DialogActions>
      </Dialog>
    </Layout>
  );
};

export default ProductDetail;
