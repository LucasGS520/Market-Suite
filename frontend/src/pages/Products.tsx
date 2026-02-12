/**
 * Página de Produtos Monitorados
 *
 * Este arquivo contém a página React responsável por listar, procurar, filtrar e
 * adicionar produtos monitorados pelo usuário.
 */

import React, { useEffect, useMemo, useRef, useState, startTransition } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box,
  Typography,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  ToggleButton,
  ToggleButtonGroup,
  Divider,
} from '@mui/material';
import Grid from '@mui/material/Grid';
import {
  Add as AddIcon,
  ViewList as ViewListIcon,
  ViewModule as ViewModuleIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
} from '@mui/icons-material';
import { AxiosError } from 'axios';
import { productsService } from '../services/productsService';
import Layout from '../components/Layout';
import { formatCurrency, normalizePriceInput } from '../utils/currency';
import type { 
  ApiErrorResponse,
  MonitoredProduct,
  MonitoredProductCreateScraping,
  MonitoredScrapeCreationResponse,
} from '../types';
import TruncatedText from '../utils/TruncatedText';
import ProductStateBadge from '../components/ProductStateBadge';
import { resolveMonitoredStatus, statusToBadge } from '../utils/productStatus';
import { renderMonitoredPrice } from '../utils/renderMonitoredPrice';
import { useToast } from '../hooks/useToast';

/**
 * Extrai a mensagem detalhada de erro retornada pelo API quando disponível
 */
const getApiErrorDetail = (error: unknown): string | undefined => {
  const axiosError = error as AxiosError<ApiErrorResponse>;
  return axiosError.response?.data?.detail;
};

/**
 * Normaliza o modo de visualização para evitar estados inválidos vindos da URL.
 */
const sanitizeViewMode = (value: string | null): 'list' | 'table' => {
  return value === 'table' ? 'table' : 'list';
};

/**
 * Normaliza o número de página garantindo inteiro positivo e fallback em 1.
 */
const sanitizePageParam = (value: string | null): number => {
  const parsedPage = Number.parseInt(value ?? '1', 10);
  return Number.isFinite(parsedPage) && parsedPage > 0 ? parsedPage : 1;
};

/**
 * Componente principal da página de Produtos Monitorados.
 * - Buscar produtos monitorados com paginação, busca e filtro de status.
 * - Permitir alternância de visualização (lista / tabela).
 * - Abrir diálogo para adicionar novo produto.
 *
 * Retorna a interface de gerenciamento de produtos.
 */
const Products: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const { showToast, dismissToast } = useToast();

  // Estado da UI
  // A URL é a fonte de verdade para preservar contexto ao navegar entre lista e detalhes.
  const [viewMode, setViewMode] = useState<'list' | 'table'>(() => sanitizeViewMode(searchParams.get('view')));
  const [searchQuery, setSearchQuery] = useState(''); // texto de busca
  const [statusFilter, setStatusFilter] = useState(''); // filtro por status de competitividade
  const [page, setPage] = useState<number>(() => sanitizePageParam(searchParams.get('page'))); // página atual para paginação em modo lista
  const listPageSize = 5; // quantidade de itens por página solicitada ao backend
  const [openAddDialog, setOpenAddDialog] = useState(false); // controla diálogo de adicionar produto
  const [newProductUrl, setNewProductUrl] = useState(''); // URL do novo produto
  const [newProductName, setNewProductName] = useState(''); // nome opcional do novo produto
  const [newCompetitorUrl, setNewCompetitorUrl] = useState(''); // URL opcional do concorrente inicial
  const previousFiltersRef = useRef<{ searchQuery: string; statusFilter: string } | null>(null); // Ref para comparar filtros anteriores e evitar reset de página desnecessário
  const currentPageRef = useRef(page); // Ref para manter a página atual durante mudanças de filtro

  /**
   * Busca quantidade total de produtos monitorados do usuário para personalizar mensagens de vazio.
   * Usa uma página mínima para reduzir tráfego enquanto ainda obtém metadados de contagem.
   */
  const { data: totalMonitored } = useQuery({
    queryKey: ['monitoredProducts', '__all__'],
    queryFn: () =>
      productsService.getMonitoredProducts({
        page: 1,
        per_page: 1,
      }),
    staleTime: 5 * 60 * 1000,
  });

  /**
   * Consulta principal de produtos monitorados
   * 
   * No modo lista, envia `page` e `per_page` para manter a paginação server-side.
   * No modo tabela, envia apenas filtros para receber o conjunto completo do backend.
   * 
   * `keepPreviousData` evita piscar a tabela/lista durante troca de página,
   * enquanto `staleTime` reduz refetch agressivo em navegação paginada rápida.
   */
  const monitoredProductsParams = useMemo(() => {
    const baseFilters = {
      query: searchQuery || undefined,
      status: statusFilter || undefined,
    };

    if (viewMode === 'list') {
      return {
        ...baseFilters,
        page,
        per_page: listPageSize,
      };
    }

    return baseFilters;
  }, [listPageSize, page, searchQuery, statusFilter, viewMode]);

  /**
   * Discriminador de cache da consulta principal.
   *
   * Incluímos explicitamente modo e estratégia de paginação para evitar colisão de cache
   * entre payloads distintos (ex.: tabela sem paginação vs lista paginada).
   */
  const monitoredProductsQueryKey = useMemo(() => {
    const paginationStrategy = viewMode === 'list' ? 'paged' : 'full';

    return [
      'monitoredProducts',
      {
        viewMode,
        paginationStrategy,
        query: searchQuery,
        status: statusFilter,
        page: viewMode === 'list' ? page : undefined,
      },
    ] as const;
  }, [page, searchQuery, statusFilter, viewMode]);

  const { data, isLoading, error } = useQuery({
    queryKey: monitoredProductsQueryKey,
    queryFn: () => productsService.getMonitoredProducts(monitoredProductsParams),
    placeholderData: viewMode === 'list' ? keepPreviousData : undefined,
    staleTime: 8 * 1000,
  });

  useEffect(() => {
    currentPageRef.current = page;
  }, [page]);

  useEffect(() => {
    if (error) {
      showToast({
        key: 'monitoring:products:load-error',
        message: 'Erro ao carregar produtos. Tente novamente.',
        severity: 'error',
        persist: true,
        replace: true,
      });
    } else {
      dismissToast('monitoring:products:load-error');
    }
  }, [dismissToast, error, showToast]);

  // Ao alterar busca/filtro, reinicia paginação para manter resultado consistente.
  useEffect(() => {
    const previousFilters = previousFiltersRef.current;
    previousFiltersRef.current = { searchQuery, statusFilter };

    // Evita reset em montagem inicial; só paginamos para 1 quando houve mudança real dos filtros.
    if (!previousFilters) {
      return;
    }

    if (currentPageRef.current !== 1) {
      startTransition(() => setPage(1));
    }
  }, [searchQuery, statusFilter]);

  // Mantém `view` na URL para evitar perda de contexto ao trocar rota.
  useEffect(() => {
    setSearchParams((previousParams) => {
      const nextParams = new URLSearchParams(previousParams);

      if (viewMode === 'list') {
        nextParams.delete('view');
      } else {
        nextParams.set('view', viewMode);
      }

      return nextParams;
    }, { replace: true });
  }, [setSearchParams, viewMode]);

  // Mantém `page` na URL para refletir paginação atual e facilitar compartilhamento.
  useEffect(() => {
    setSearchParams((previousParams) => {
      const nextParams = new URLSearchParams(previousParams);

      if (page <= 1) {
        nextParams.delete('page');
      } else {
        nextParams.set('page', String(page));
      }

      return nextParams;
    }, { replace: true });
  }, [page, setSearchParams]);

  /**
   * Normaliza valores para comparação numérica evitando zeros como preços válidos
   */
  const parseToNumber = (value: string | number | null | undefined) => {
    return normalizePriceInput(value);
  };
  /**
   * Itens visíveis na UI para ambos os modos.
   *
   * Em lista: backend já retorna o recorte paginado.
   * Em tabela: backend retorna todos os itens filtrados.
   */
  const visibleItems = useMemo(() => {
    if (!data?.items) return [] as MonitoredProduct[];

    return data.items;
  }, [data]);

  const totalPages = useMemo(() => {
    if (viewMode !== 'list') return 1;

    const totalItems = data?.meta?.total ?? 0;
    return Math.max(1, Math.ceil(totalItems / listPageSize));
  }, [data?.meta?.total, listPageSize, viewMode]);

  useEffect(() => {
    if (viewMode !== 'list') return;

    if (page > totalPages) {
      startTransition(() => setPage(totalPages));
    }
  }, [page, totalPages, viewMode]);

  const handlePageSelect = (newPage: number) => {
    const boundedPage = Math.min(Math.max(newPage, 1), totalPages);
    setPage(boundedPage);
  };

  /**
   * Troca o modo de visualização mantendo o estado refletido na URL.
   */
  const handleViewModeChange = (_: React.MouseEvent<HTMLElement>, newMode: 'list' | 'table' | null) => {
    if (!newMode) return;
    setViewMode(newMode);
  };

  /**
   * Navega para detalhes preservando os filtros/página atuais via query string.
   */
  const navigateToProductDetail = (productId: string) => {
    const currentSearch = searchParams.toString();
    navigate({
      pathname: `/product/${productId}`,
      search: currentSearch ? `?${currentSearch}` : '',
    });
  };

  // Mutation para criação de produto monitorado.
  const createProductMutation = useMutation({
    mutationFn: productsService.createMonitoredProduct,
    onSuccess: (data: MonitoredScrapeCreationResponse) => {
      // Invalida cache para forçar refresh da lista atualizada
      queryClient.invalidateQueries({ queryKey: ['monitoredProducts'] });
      queryClient.invalidateQueries({ queryKey: ['monitoredProducts', '__all__'] });
      // Fecha diálogo e reseta campos do formulário
      setOpenAddDialog(false);
      setNewProductUrl('');
      setNewProductName('');
      setNewCompetitorUrl('');
      const successMessage = 
        data.message ||
        'Produto criado e scraping em andamento. A lista será atualizada automaticamente.';
      showToast({
        key: 'monitoring:product:create',
        message: successMessage,
        severity: 'info',
        replace: true,
      });
      const competitorWarning = data.competitor_warning || data.competitor_error;
      if (competitorWarning) {
        showToast({
          key: 'monitoring:product:create:competitor',
          message: `Produto criado com sucesso, mas o concorrente não pôde ser adicionado: ${competitorWarning}`,
          severity: 'warning',
          replace: true,
        });
      }
    },
    onError: (error) => {
      // Mantém mensagem amigável para orientar ajuste de URL ou reautenticação
      const apiMessage = getApiErrorDetail(error);
      showToast({
        key: 'monitoring:product:create:error',
        message: apiMessage || 'Não foi possível criar o produto. Verifique a URL e tente novamente.',
        severity: 'error',
        persist: true,
        replace: true,
      });
    },
  });

  /**
   * Handler para enviar criação de novo produto.
   * Valida presença de URL antes de disparar mutation.
   */
  const handleAddProduct = () => {
    if (!newProductUrl) return;
    const payload: MonitoredProductCreateScraping = {
      product_url: newProductUrl,
      name_identification: newProductName || undefined,
    };

    if (newCompetitorUrl) {
      payload.initial_competitor = {
        product_url: newCompetitorUrl,
      };
    }

    createProductMutation.mutate(payload);
  };

  const getDifferenceValue = (product: MonitoredProduct) => {
    const potentialAdjustment = product.comparison_summary?.potential_adjustment;
    if (potentialAdjustment !== null && potentialAdjustment !== undefined) {
      const adjustmentValue = parseToNumber(potentialAdjustment);
      if (adjustmentValue !== null) {
        return adjustmentValue;
      }
    }

    const monitoredPrice = parseToNumber(product.current_price);
    const lowestCompetitorPrice = parseToNumber(product.comparison_summary?.competitors_min);

    if ((product.comparison_summary?.competitors_with_price_count ?? 0) === 0) {
      return null;
    }

    if (monitoredPrice !== null && lowestCompetitorPrice !== null) {
      return monitoredPrice - lowestCompetitorPrice;
    }

    return null;
  };

  const getRankingLabel = (product: MonitoredProduct) => {
    const positionRank = product.comparison_summary?.position_rank;
    const competitorsCount = product.comparison_summary?.competitors_count ?? 0;

    if (positionRank === null || positionRank === undefined) {
      return 'Ranking —';
    }

    const totalSellers = competitorsCount + 1; // inclui o produto monitorado
    return `Ranking #${positionRank} de ${totalSellers}`;
  };

  /**
   * Prioriza o total filtrado retornado em `data.meta.total` para que as
   * mensagens de empty state reflitam primeiro o universo filtrado atual.
   */
  const totalCount = useMemo(() => {
    const filteredTotal = data?.meta?.total;
    const globalTotal = totalMonitored?.meta?.total;

    const hasActiveFilters = Boolean(searchQuery || statusFilter);

    if (hasActiveFilters) {
      return filteredTotal ?? visibleItems.length;
    }

    return filteredTotal ?? globalTotal ?? visibleItems.length;
  }, [
    data?.meta?.total,
    totalMonitored?.meta?.total,
    searchQuery,
    statusFilter,
    visibleItems.length,
  ]);

  /**
   * Define cor do destaque visual com base no badge centralizado.
   */
  const resolveVisualEmphasis = (product: MonitoredProduct) => {
    const status = resolveMonitoredStatus(product);
    const badgeMeta = statusToBadge[status] ?? statusToBadge.unknown;
    const isInactive = status === 'inactive';
    const isPaused = (product.paused ?? product.is_paused) ?? false;

    const borderColorMap: Record<string, string> = {
      success: 'success.light',
      warning: 'warning.light',
      error: 'error.light',
      default: 'divider',
      info: 'info.light',
    };

    const colorKey = badgeMeta.color ?? 'default';
    const borderColor = isPaused ? 'warning.light' : borderColorMap[colorKey] || 'divider';
    const backgroundColor = isInactive ? 'grey.50' : 'background.paper';

    return {
      chipColor: badgeMeta.color,
      borderColor,
      backgroundColor,
      isInactive,
      isPaused,
      status,
    };
  };

  return (
    <Layout>
      {/* Cabeçalho */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" gutterBottom>
          Produtos Monitorados
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Gerencie e visualize todos os seus produtos monitorados
        </Typography>
      </Box>

      {/* Barra de Ações */}
      <Box sx={{ mb: 3, display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setOpenAddDialog(true)}
        >
          Adicionar Seu Produto
        </Button>

        <TextField
          size="small"
          placeholder="Buscar Produtos..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          sx={{ minWidth: 200 }}
        />

        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel>Status</InputLabel>
          <Select
            value={statusFilter}
            label="Status"
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <MenuItem value="">Todos</MenuItem>
            <MenuItem value="competitivo">Competitivo</MenuItem>
            <MenuItem value="atencao">Atenção</MenuItem>
            <MenuItem value="urgente">Urgente</MenuItem>
          </Select>
        </FormControl>

        {/* Espaço flexível para empurrar os botões do lado direito */}
        <Box sx={{ flexGrow: 1 }} />

        {/* Alterna entre visualização em lista e tabela */}
        <ToggleButtonGroup
          value={viewMode}
          exclusive
          onChange={handleViewModeChange}
          size="small"
        >
          <ToggleButton value="list">
            <ViewListIcon />
          </ToggleButton>
          <ToggleButton value="table">
            <ViewModuleIcon />
          </ToggleButton>
        </ToggleButtonGroup>
      </Box>

      {/* Conteúdo */}
      {isLoading ? (
        // Estado de carregamento
        <Box display="flex" justifyContent="center" py={4}>
          <CircularProgress />
        </Box>
      ) : error ? (
        // Estado de erro ao buscar produtos
        <Typography color="error">Erro ao carregar produtos. Tente novamente.</Typography>
      ) : visibleItems && visibleItems.length > 0 ? (
        viewMode === 'list' ? (
          // Modo Lista - exibe cartões por produto
          <Grid container spacing={3}>
            {visibleItems.map((product) => {
              const competitorsWithPrice = product.comparison_summary?.competitors_with_price_count ?? 0;
              const lowestCompetitorLabel =
                competitorsWithPrice > 0
                  ? formatCurrency(product.comparison_summary?.competitors_min, { fallbackLabel: '—' })
                  : '—';
              const differenceValue = getDifferenceValue(product);
              const differenceLabel = formatCurrency(differenceValue, {
                allowZero: true,
                fallbackLabel: '—',
              });

              const monitoredPriceNum = parseToNumber(product.current_price);
              const lowestPriceNum = parseToNumber(product.comparison_summary?.competitors_min);

              // cor do menor concorrente: verde quando concorrente maior (sou mais barato),
              // vermelho quando concorrente menor (sou mais caro), preto quando igual/indisponível
              let lowestColor = 'text.primary';
              if (lowestPriceNum !== null && monitoredPriceNum !== null) {
                if (lowestPriceNum > monitoredPriceNum) lowestColor = 'success.main';
                else if (lowestPriceNum < monitoredPriceNum) lowestColor = 'error.main';
                else lowestColor = 'text.primary';
              }

              // ícone e cor da diferença: >0 -> seta pra cima (vermelha), <0 -> seta pra baixo (verde), 0/null -> neutro
              let diffIconComponent = <TrendingUpIcon color="primary" />;
              let diffTextColor = 'text.primary';
              if (differenceValue !== null) {
                if (differenceValue > 0) {
                  diffIconComponent = <TrendingUpIcon color="error" />;
                  diffTextColor = 'error.main';
                } else if (differenceValue < 0) {
                  diffIconComponent = <TrendingDownIcon color="success" />;
                  diffTextColor = 'success.main';
                } else {
                  diffIconComponent = <TrendingUpIcon color="primary" />;
                  diffTextColor = 'text.primary';
                }
              }

              const activeCompetitors =
                product.comparison_summary?.competitors_with_price_count ??
                product.comparison_summary?.competitors_count ??
                0;
              const rankingLabel = `${getRankingLabel(product)} | ${activeCompetitors} Concorrentes`;
              const visualEmphasis = resolveVisualEmphasis(product);

              return (
                <Grid item xs={12} key={product.id}>
                  <Card
                    elevation={visualEmphasis.isInactive ? 0 : 2}
                    sx={{
                      border: '1px solid',
                      borderColor: viewMode === 'list' ? visualEmphasis.borderColor : 'divider',
                      backgroundColor: visualEmphasis.backgroundColor,
                      opacity: visualEmphasis.isPaused ? 0.5 : visualEmphasis.isInactive ? 0.7 : 1,
                    }}
                  >
                    <CardContent>
                      <Box display="flex" gap={2}>
                        {product.thumbnail && (
                          <Box
                            component="img"
                            src={product.thumbnail}
                            alt={product.name}
                            sx={{
                              width: 100,
                              height: 100,
                              objectFit: 'cover',
                              borderRadius: 1,
                            }}
                          />
                        )}
                        <Box flex={1}>
                          <Box display="flex" justifyContent="space-between" alignItems="start">
                            <Box>
                              <TruncatedText
                                text={product.name}
                                variant="h6"
                                lines={2}
                                maxWidth={420}
                              />
                              <TruncatedText
                                text={`Origem: ${new URL(product.url).hostname}`}
                                variant="body2"
                                color="text.secondary"
                                maxWidth={420}
                              />
                            </Box>
                            <ProductStateBadge product={product} />
                          </Box>

                          {/* Informações de preço resumidas */}
                          <Grid container spacing={2} sx={{ mt: 2 }}>
                            <Grid item xs={4}>
                              <Typography variant="body2" color="text.secondary">
                                MEU PREÇO
                              </Typography>
                              {renderMonitoredPrice(product, { variant: 'h5' })}
                            </Grid>
                            <Grid item xs={4}>
                              <Typography variant="body2" color="text.secondary">
                                MENOR CONCORRENTE
                              </Typography>
                                <Typography variant="h5" sx={{ color: lowestColor }}>
                                  {lowestCompetitorLabel}
                                </Typography>
                            </Grid>
                            <Grid item xs={4}>
                              <Typography variant="body2" color="text.secondary">
                                DIFERENÇA
                              </Typography>
                              <Box display="flex" alignItems="center" gap={0.5}>
                                {diffIconComponent}
                                <Typography variant="h5" sx={{ color: diffTextColor }}>
                                  {differenceLabel}
                                </Typography>
                              </Box>
                            </Grid>
                          </Grid>
                          
                          {/* Rodapé do cartão com ações */}
                          <Box display="flex" justifyContent="space-between" alignItems="center" mt={2}>
                            <Typography variant="body2" color="text.secondary">
                              {rankingLabel}
                            </Typography>
                            <Box display="flex" gap={1}>
                              <Button
                                variant="outlined"
                                color="secondary"
                                size="small"
                                component="a"
                                href={product.url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                Ver Anúncio
                              </Button>
                              <Button
                                variant="contained"
                                size="small"
                                onClick={() => navigateToProductDetail(product.id)}
                              >
                                Ver Detalhes
                              </Button>
                            </Box>
                          </Box>
                        </Box>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              );
            })}
            {totalPages > 1 && (
              <Grid item xs={12}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mt={2}>
                  <Button
                    variant="outlined"
                    disabled={page <= 1}
                    onClick={() => handlePageSelect(page - 1)}
                  >
                    Anterior
                  </Button>

                  <Typography variant="body2" color="text.secondary">
                    Página {page} de {totalPages}
                  </Typography>

                  <Button
                    variant="outlined"
                    disabled={page >= totalPages}
                    onClick={() => handlePageSelect(page + 1)}
                  >
                    Próxima
                  </Button>
                </Box>
              </Grid>
            )}
          </Grid>
        ) : (
          // Modo Tabela - exibe produtos em linhas
          <TableContainer component={Paper} elevation={2}>
            <Table sx={{ tableLayout: 'fixed' }}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: 380 }}>Produto</TableCell>
                  <TableCell align="right" sx={{ width: 160 }}>
                    Meu Preço
                  </TableCell>
                  <TableCell align="right" sx={{ width: 180 }}>
                    Menor Concorrente
                  </TableCell>
                  <TableCell align="right" sx={{ width: 140 }}>
                    Diferença
                  </TableCell>
                  <TableCell align="center" sx={{ width: 140 }}>
                    Concorrentes
                  </TableCell>
                  <TableCell align="center" sx={{ width: 140 }}>
                    Ranking
                  </TableCell>
                  <TableCell align="center" sx={{ width: 140 }}>
                    Status
                  </TableCell>
                  <TableCell align="center" sx={{ width: 200 }}>
                    Ações
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {visibleItems.map((product) => {
                  const competitorsWithPrice = product.comparison_summary?.competitors_with_price_count ?? 0;
                  const lowestCompetitorLabel =
                    competitorsWithPrice > 0
                      ? formatCurrency(product.comparison_summary?.competitors_min, { fallbackLabel: '—' })
                      : '—';
                  const differenceValue = getDifferenceValue(product);
                  const differenceLabel = formatCurrency(differenceValue, {
                    allowZero: true,
                    fallbackLabel: '—',
                  });

                  const monitoredPriceNum = parseToNumber(product.current_price);
                  const lowestPriceNum = parseToNumber(product.comparison_summary?.competitors_min);

                  let lowestColor = 'text.primary';
                  if (lowestPriceNum !== null && monitoredPriceNum !== null) {
                    if (lowestPriceNum > monitoredPriceNum) lowestColor = 'success.main';
                    else if (lowestPriceNum < monitoredPriceNum) lowestColor = 'error.main';
                  }

                  const competitorsCount =
                    product.comparison_summary?.competitors_with_price_count ??
                    product.comparison_summary?.competitors_count ??
                    0;
                  const rankingLabel = getRankingLabel(product);
                  const isCheaperOrEqual = differenceValue !== null ? differenceValue <= 0 : null;

                  const visualEmphasis = resolveVisualEmphasis(product);

                  return (
                    <TableRow
                      key={product.id}
                      hover={!visualEmphasis.isInactive}
                      selected={visualEmphasis.isInactive}
                      sx={{ opacity: visualEmphasis.isPaused ? 0.5 : visualEmphasis.isInactive ? 0.7 : 1 }}
                    >
                      <TableCell sx={{ maxWidth: 380, width: 380 }}>
                        <Box display="flex" alignItems="center" gap={1}>
                          {product.thumbnail && (
                            <Box
                              component="img"
                              src={product.thumbnail}
                              alt={product.name}
                              sx={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 1 }}
                            />
                          )}
                          <Box sx={{ maxWidth: 300, display: 'flex', flexDirection: 'column', gap: 0.25 }}>
                            <TruncatedText text={product.name} variant="body2" lines={2} maxWidth={300} />
                            <TruncatedText
                              text={new URL(product.url).hostname}
                              variant="caption"
                              color="text.secondary"
                              maxWidth={300}
                            />
                          </Box>
                        </Box>
                      </TableCell>
                      <TableCell align="right">
                        {renderMonitoredPrice(product, { align: 'right' })}
                      </TableCell>
                      <TableCell align="right">
                        <Typography sx={{ color: lowestColor }}>{lowestCompetitorLabel}</Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Typography
                          sx={{
                            color:
                              isCheaperOrEqual === null
                                ? 'text.primary'
                                : isCheaperOrEqual
                                  ? 'success.main'
                                  : 'error.main',
                          }}
                        >
                          {differenceLabel}
                        </Typography>
                      </TableCell>
                      <TableCell align="center">{competitorsCount}</TableCell>
                      <TableCell align="center">{rankingLabel}</TableCell>
                      <TableCell align="center">
                        <ProductStateBadge product={product} />
                      </TableCell>
                      <TableCell align="center">
                        <Box display="flex" justifyContent="center" gap={1}>
                          <Button
                            variant="outlined"
                            color="secondary"
                            size="small"
                            component="a"
                            href={product.url}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            Ver Anúncio
                          </Button>
                          <Button
                            variant="contained"
                            size="small"
                            onClick={() => navigateToProductDetail(product.id)}
                          >
                            Ver Detalhes
                          </Button>
                        </Box>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        )
      ) : (
        // Estado vazio com mensagens contextualizadas
        <Card elevation={0} sx={{ border: '1px dashed', borderColor: 'divider', p: 3 }}>
          <CardContent sx={{ textAlign: 'center' }}>
            <Typography variant="h6" gutterBottom>
              {totalCount === 0
                ? 'Nenhum produto monitorado.'
                : 'Nenhum produto corresponde aos filtros selecionados.'}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {totalCount === 0
                ? 'Adicione seu primeiro produto para começar a acompanhar os preços.'
                : 'Tente outro filtro ou limpe a busca para visualizar seus produtos.'}
            </Typography>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => setOpenAddDialog(true)}
            >
              {totalCount === 0 ? 'Adicionar seu produto' : 'Adicionar novo produto'}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Dialog de Adicionar Produto */}
      <Dialog open={openAddDialog} onClose={() => setOpenAddDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Adicionar Produto Monitorado</DialogTitle>
        <DialogContent>
          <TextField
            margin="dense"
            label="Nome de Identificação"
            type="text"
            fullWidth
            value={newProductName}
            onChange={(e) => setNewProductName(e.target.value)}
            placeholder="Ex: Monitor Gamer 27''"
          />
          <TextField
            autoFocus
            margin="dense"
            label="URL do Produto"
            type="url"
            fullWidth
            required
            value={newProductUrl}
            onChange={(e) => setNewProductUrl(e.target.value)}
            placeholder="https://exemplo.com/produto"
          />
          <Divider sx={{ my: 2 }} />
          <TextField
            margin="dense"
            label="Adicionar Concorrente (opcional)"
            type="url"
            fullWidth
            value={newCompetitorUrl}
            onChange={(e) => setNewCompetitorUrl(e.target.value)}
            placeholder="https://exemplo.com/concorrente"
          />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            O produto será processado de forma assíncrona. Caso informe um concorrente, ele será criado junto ao monitorado.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenAddDialog(false)} color="secondary">
            Cancelar
          </Button>
          <Button
            onClick={handleAddProduct}
            variant="contained"
            disabled={!newProductUrl || createProductMutation.isPending}
          >
            {createProductMutation.isPending ? <CircularProgress size={24} /> : 'Adicionar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Layout>
  );
};

export default Products;
