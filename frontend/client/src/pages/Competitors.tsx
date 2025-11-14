/**
 * Página dedicada para gestão de concorrentes de um monitorado.
 *
 * - Apresenta cabeçalho com dados do produto e resumo competitivo.
 * - Permite filtrar, ordenar, paginar e executar ações em massa sobre concorrentes.
 * - Integra modal card-first para adicionar novos concorrentes com feedback otimista.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useLocation, useRoute } from 'wouter';
import { toast } from 'sonner';
import { ArrowLeft, Check, Loader2, RefreshCw, Search } from 'lucide-react';
import { Badge } from '@/components/ui/data-display/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/data-display/card';
import { Skeleton } from '@/components/ui/data-display/skeleton';
import { Button } from '@/components/ui/button/button';
import { Input } from '@/components/ui/inputs/input';
import { Checkbox } from '@/components/ui/inputs/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/inputs/select';
import { Pagination, PaginationContent, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from '@/components/ui/navigation/pagination';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/navigation/tabs';
import AddCompetitorModal from '@/components/modals/AddCompetitorModal';
import { getComparisonSummary, getCompetitors, getMonitoredProduct, pauseCompetitors, removeCompetitors, resumeCompetitors, type Competitor, type CompetitorBulkActionPayload, type ComparisonSummary, type MonitoredProduct } from '@/lib/api';
import { formatCurrency, formatRelativeTime } from '@/lib/helpers';
import { CompetitorCard } from '@/components/CompetitorCard';
import { BulkActionsBar } from '@/components/BulkActionsBar';

/**
 * Normaliza o identificador do produto removendo querystrings e barras ao final.
 * - Recebe um id cru possivelmente vindo da rota e retorna a versão limpa.
 */
export const sanitizedProductId = (rawId: string | undefined | null): string => {
  if (!rawId) {
    return '';
  }

  const [withoutQuery] = rawId.split('?');
  return withoutQuery.replace(/\/+$/, '');
};

/** Quantidade padrão de concorrentes carregados por página. */
const COMPETITORS_PER_PAGE = 20;

/** Tempo (ms) utilizado para debounce de busca. */
const SEARCH_DEBOUNCE_MS = 400;

/**
 * Define opções de ordenação exibidas para o usuário.
 * - Mantém os valores esperados pela API.
 */
const sortOptions: Array<{ value: 'price' | 'last_checked' | 'price_change'; label: string }> = [
  { value: 'last_checked', label: 'Última coleta' },
  { value: 'price', label: 'Preço' },
  { value: 'price_change', label: 'Variação' },
];

/**
 * Define filtros de status disponíveis na UI.
 */
const statusFilterOptions: Array<{ value: 'all' | Competitor['status']; label: string }> = [
  { value: 'all', label: 'Todos' },
  { value: 'available', label: 'Em estoque' },
  { value: 'unavailable', label: 'Indisponível' },
  { value: 'removed', label: 'Removido' },
];

/**
 * Página principal de concorrentes.
 * - Responsável por carregar produto, resumo e lista de concorrentes.
 * - Contém filtros, paginação e integração com modal de criação.
 */
const CompetitorsPage: React.FC = () => {
  const { token } = useAuth();
  const [, navigate] = useLocation();
  const [, routeParams] = useRoute<{ id?: string; rest?: string }>('/competitors/:id/:rest*');

  // Id do produto extraído e normalizado da rota
  const productId = sanitizedProductId(routeParams?.id ?? null);

  // Estado do produto monitorado (detalhes)
  const [product, setProduct] = useState<MonitoredProduct | null>(null);
  const [productError, setProductError] = useState<string | null>(null);
  const [isLoadingProduct, setIsLoadingProduct] = useState(true);

  // Resumo comparativo (métricas agregadas)
  const [summary, setSummary] = useState<ComparisonSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);

  // Lista paginada de concorrentes
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [totalCompetitors, setTotalCompetitors] = useState(0);
  const [isLoadingCompetitors, setIsLoadingCompetitors] = useState(false);
  const [competitorsError, setCompetitorsError] = useState<string | null>(null);

  // Controles de UI: paginação, busca, filtros e ordenação
  const [page, setPage] = useState(1);
  const [searchValue, setSearchValue] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | Competitor['status']>('all');
  const [sortBy, setSortBy] = useState<'price' | 'last_checked' | 'price_change'>('last_checked');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [includePaused, setIncludePaused] = useState(true);

  // Seleção e processamento por item / em massa
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isBulkProcessing, setIsBulkProcessing] = useState(false);
  const [processingIds, setProcessingIds] = useState<Set<string>>(new Set());

  // Modal de adicionar concorrente
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);

  // Ref para gerenciar debounce de busca
  const debounceTimeoutRef = useRef<number | null>(null);

  /**
   * Debounce da busca: atualiza debouncedSearch após timeout.
   * - Reinicia página para 1 sempre que nova busca for aplicada.
   */
  useEffect(() => {
    if (debounceTimeoutRef.current) {
      window.clearTimeout(debounceTimeoutRef.current);
    }

    debounceTimeoutRef.current = window.setTimeout(() => {
      setDebouncedSearch(searchValue.trim());
      setPage(1);
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      if (debounceTimeoutRef.current) {
        window.clearTimeout(debounceTimeoutRef.current);
      }
    };
  }, [searchValue]);

  // Calcula total de páginas com base no total de concorrentes
  const totalPages = useMemo(() => {
    if (totalCompetitors === 0) {
      return 1;
    }
    return Math.max(1, Math.ceil(totalCompetitors / COMPETITORS_PER_PAGE));
  }, [totalCompetitors]);

  // Reinicia paginação quando filtros/ordenacao mudam
  useEffect(() => {
    setPage(1);
  }, [statusFilter, sortBy, sortDirection, includePaused]);

  // Limpa seleção
  const resetSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  /**
   * Carrega detalhes do produto monitorado.
   * - Exibe erro quando token ou id ausente.
   */
  const loadProduct = useCallback(async () => {
    if (!token) {
      setProductError('Sessão expirada. Faça login novamente.');
      setIsLoadingProduct(false);
      return;
    }

    if (!productId) {
      setProductError('Produto não encontrado na rota.');
      setIsLoadingProduct(false);
      return;
    }

    setIsLoadingProduct(true);
    setProductError(null);

    try {
      const data = await getMonitoredProduct(token, productId);
      setProduct(data);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao carregar produto monitorado.';
      setProductError(message);
      toast.error(message);
    } finally {
      setIsLoadingProduct(false);
    }
  }, [token, productId]);

  /**
   * Carrega resumo competitivo (métricas agregadas).
   */
  const loadSummary = useCallback(async () => {
    if (!token || !productId) {
      return;
    }

    setIsLoadingSummary(true);
    setSummaryError(null);

    try {
      const data = await getComparisonSummary(token, productId);
      setSummary(data);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao carregar resumo competitivo.';
      setSummaryError(message);
    } finally {
      setIsLoadingSummary(false);
    }
  }, [token, productId]);

  /**
   * Carrega lista de concorrentes conforme filtros/paginação.
   * - Reseta seleção ao completar a carga.
   */
  const loadCompetitors = useCallback(async () => {
    if (!token || !productId) {
      return;
    }

    setIsLoadingCompetitors(true);
    setCompetitorsError(null);

    try {
      const response = await getCompetitors(token, productId, {
        page,
        per_page: COMPETITORS_PER_PAGE,
        search: debouncedSearch || undefined,
        status: statusFilter === 'all' ? undefined : statusFilter,
        include_paused: includePaused,
        sort_by: sortBy,
        sort_direction: sortDirection,
      });

      setCompetitors(response.items);
      setTotalCompetitors(response.total);
      resetSelection();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao listar concorrentes.';
      setCompetitorsError(message);
      toast.error(message);
    } finally {
      setIsLoadingCompetitors(false);
    }
  }, [token, productId, page, debouncedSearch, statusFilter, includePaused, sortBy, sortDirection, resetSelection]);

  // Efeitos para carregar dados iniciais
  useEffect(() => {
    void loadProduct();
  }, [loadProduct]);

  useEffect(() => {
    void loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    void loadCompetitors();
  }, [loadCompetitors]);

  /**
   * Executa ação em massa (ou por item) contra API: pause / resume / remove.
   * - Quando ids.length === 1 atualiza processingIds para indicar loading por item.
   * - Quando múltiplos ids altera isBulkProcessing.
   * - Após sucesso, recarrega lista e resumo.
   */
  const runBulkAction = useCallback(
    async (ids: string[], action: 'pause' | 'resume' | 'remove') => {
      if (!token || !productId || ids.length === 0) {
        return;
      }

      const payload: CompetitorBulkActionPayload = {
        monitored_product_id: productId,
        competitor_ids: ids,
      };

      const singleId = ids.length === 1 ? ids[0] : null;
      if (singleId) {
        setProcessingIds((previous) => new Set(previous).add(singleId));
      } else {
        setIsBulkProcessing(true);
      }

      try {
        if (action === 'pause') {
          await pauseCompetitors(token, payload);
          toast.success('Concorrentes pausados com sucesso.');
        } else if (action === 'resume') {
          await resumeCompetitors(token, payload);
          toast.success('Concorrentes retomados com sucesso.');
        } else {
          await removeCompetitors(token, payload);
          toast.success('Concorrentes removidos com sucesso.');
        }

        // Recarrega dados após alteração de estado
        await Promise.all([loadCompetitors(), loadSummary()]);
      } catch (error) {
        const message =
          error instanceof Error ? error.message : 'Não foi possível concluir a ação selecionada.';
        toast.error(message);
      } finally {
        if (singleId) {
          setProcessingIds((previous) => {
            const next = new Set(previous);
            next.delete(singleId);
            return next;
          });
        } else {
          setIsBulkProcessing(false);
        }
      }
    },
    [token, productId, loadCompetitors, loadSummary],
  );

  // Toggle de seleção de item individual
  const handleToggleSelection = useCallback(
    (id: string) => {
      setSelectedIds((previous) => {
        const next = new Set(previous);
        if (next.has(id)) {
          next.delete(id);
        } else {
          next.add(id);
        }
        return next;
      });
    },
    [],
  );

  // Seleciona / deseleciona todos os itens da página atual
  const handleToggleSelectAll = useCallback(() => {
    setSelectedIds((previous) => {
      if (competitors.length === 0) {
        return new Set();
      }
      if (previous.size === competitors.length) {
        return new Set();
      }
      return new Set(competitors.map((item) => item.id));
    });
  }, [competitors]);

  const selectedCount = selectedIds.size;
  const isEmptyState = !isLoadingCompetitors && competitors.length === 0 && !competitorsError;
  const handlePageChange = (nextPage: number) => {
    setPage(nextPage);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // UI principal da página
  return (
<div className="space-y-6">
  <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
    <div className="flex items-center gap-3">
      {/* Botão de voltar para lista de produtos */}
      <Button variant="ghost" size="icon" onClick={() => navigate('/products')}>
        <ArrowLeft className="h-4 w-4" />
      </Button>
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Concorrentes</h1>
        {product && (
          <p className="text-sm text-muted-foreground">
            {product.name_identification ?? 'Produto sem identificação'} • {formatCurrency(product.current_price)}
          </p>
        )}
      </div>
    </div>

    {/* Botão manual para atualizar o resumo competitivo (mostra spinner quando carregando) */}
    <Button
      type="button"
      variant="outline"
      className="gap-2"
      onClick={() => void loadSummary()}
      disabled={isLoadingSummary}
    >
      <RefreshCw className={`h-4 w-4 ${isLoadingSummary ? 'animate-spin' : ''}`} />
      Atualizar resumo
    </Button>
  </div>

  <Tabs value="competitors" className="w-full">
    <TabsList className="w-full justify-start gap-2 bg-transparent">
      <TabsTrigger value="competitors" className="gap-2">
        <Check className="h-4 w-4" /> Concorrentes
      </TabsTrigger>
      <TabsTrigger value="collections" disabled className="gap-2">
        <Loader2 className="h-4 w-4" /> Histórico de Coletas
      </TabsTrigger>
      <TabsTrigger value="comparisons" disabled className="gap-2">
        <Loader2 className="h-4 w-4" /> Histórico de Comparações
      </TabsTrigger>
      <TabsTrigger value="notifications" disabled className="gap-2">
        <Loader2 className="h-4 w-4" /> Notificações
      </TabsTrigger>
    </TabsList>

    <TabsContent value="competitors" className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Resumo competitivo</CardTitle>
            <CardDescription>
              Última comparação:{' '}
              {summary?.last_comparison_at ? formatRelativeTime(summary.last_comparison_at) : 'Ainda não executada'}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <div>
              <p className="text-xs text-muted-foreground">Média dos concorrentes</p>
              <p className="text-lg font-semibold">{formatCurrency(summary?.competitors_mean ?? null)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Menor preço</p>
              <p className="text-lg font-semibold">{formatCurrency(summary?.competitors_min ?? null)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Maior preço</p>
              <p className="text-lg font-semibold">{formatCurrency(summary?.competitors_max ?? null)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Posição do monitorado</p>
              <p className="text-lg font-semibold">
                {summary?.position_rank ? `${summary.position_rank}º de ${summary?.competitors_with_price_count ?? 0}` : 'Sem ranking'}
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Estado do monitorado</CardTitle>
            <CardDescription>
              Status atual e últimas interações do monitorado selecionado.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {isLoadingProduct ? (
              <Skeleton className="h-24 w-full" />
            ) : product ? (
              <>
                <div>
                  <p className="text-xs text-muted-foreground">Status</p>
                  <p className="text-sm font-medium capitalize">{product.status}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Concorrentes ativos</p>
                  <p className="text-sm font-medium">{product.competitors_count ?? 0}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Última coleta</p>
                  <p className="text-sm font-medium">{formatRelativeTime(product.last_checked)}</p>
                </div>
              </>
            ) : (
              <p className="text-sm text-destructive">{productError}</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-3 py-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex w-full items-center gap-2 lg:w-auto">
            <Search className="h-4 w-4 text-muted-foreground" />
            {/* Campo de busca com debounce */}
            <Input
              placeholder="Buscar por nome ou loja"
              value={searchValue}
              onChange={(event) => setSearchValue(event.target.value)}
              className="w-full lg:w-72"
            />
          </div>

          <div className="flex w-full flex-col gap-3 lg:w-auto lg:flex-row">
            {/* Filtro por status */}
            <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as typeof statusFilter)}>
              <SelectTrigger className="lg:w-48">
                <SelectValue placeholder="Filtrar status" />
              </SelectTrigger>
              <SelectContent>
                {statusFilterOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Ordenação (campo) */}
            <Select value={sortBy} onValueChange={(value) => setSortBy(value as typeof sortBy)}>
              <SelectTrigger className="lg:w-48">
                <SelectValue placeholder="Ordenar por" />
              </SelectTrigger>
              <SelectContent>
                {sortOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Ordenação (direção asc/desc) */}
            <Select value={sortDirection} onValueChange={(value) => setSortDirection(value as typeof sortDirection)}>
              <SelectTrigger className="lg:w-36">
                <SelectValue placeholder="Direção" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="asc">Ascendente</SelectItem>
                <SelectItem value="desc">Descendente</SelectItem>
              </SelectContent>
            </Select>

            {/* Toggle para incluir itens pausados */}
            <div className="flex items-center gap-2">
              <Checkbox
                id="include-paused"
                checked={includePaused}
                onCheckedChange={(checked) => setIncludePaused(Boolean(checked))}
              />
              <label htmlFor="include-paused" className="text-sm">
                Mostrar pausados
              </label>
            </div>

            {/* Abre modal para adicionar novo concorrente */}
            <Button type="button" className="gap-2" onClick={() => setIsAddModalOpen(true)}>
              Adicionar concorrente
            </Button>
          </div>
        </CardContent>
      </Card>

      {summaryError && (
        <Card className="border-amber-200 dark:border-amber-900">
          <CardContent className="py-4 text-sm text-amber-600 dark:text-amber-400">{summaryError}</CardContent>
        </Card>
      )}

      {competitorsError && (
        <Card className="border-red-200 dark:border-red-800">
          <CardContent className="py-4 text-sm text-red-600 dark:text-red-400">{competitorsError}</CardContent>
        </Card>
      )}

      {selectedCount > 0 && (
        <BulkActionsBar
          selectedCount={selectedCount}
          totalCount={competitors.length}
          onPause={() => runBulkAction(Array.from(selectedIds), 'pause')}
          onResume={() => runBulkAction(Array.from(selectedIds), 'resume')}
          onRemove={() => runBulkAction(Array.from(selectedIds), 'remove')}
          onClear={resetSelection}
          isProcessing={isBulkProcessing}
        />
      )}

      <Card className="border-dashed">
        <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            {/* Checkbox para selecionar todos os concorrentes exibidos na página */}
            <Checkbox
              checked={competitors.length > 0 && selectedCount === competitors.length}
              onCheckedChange={handleToggleSelectAll}
              aria-label="Selecionar todos"
            />
            <span className="text-sm text-muted-foreground">Selecionar todos ({competitors.length})</span>
          </div>
          <span className="text-xs text-muted-foreground">
            Exibindo página {page} de {totalPages} • {totalCompetitors} concorrentes no total
          </span>
        </CardContent>
      </Card>

      {isLoadingCompetitors ? (
        <div className="space-y-4">
          {/* Placeholders (skeletons) durante carregamento da lista */}
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-40 w-full" />
          ))}
        </div>
      ) : isEmptyState ? (
        <Card>
          <CardContent className="py-16 text-center">
            <p className="text-sm text-muted-foreground">
              Nenhum concorrente encontrado com os filtros atuais. Tente ajustar os critérios ou adicione um novo concorrente.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {competitors.map((competitor) => (
            <CompetitorCard
              key={competitor.id}
              competitor={competitor}
              isSelected={selectedIds.has(competitor.id)}
              onToggleSelection={handleToggleSelection}
              onPause={(id) => runBulkAction([id], 'pause')}
              onResume={(id) => runBulkAction([id], 'resume')}
              onRemove={(id) => runBulkAction([id], 'remove')}
              isProcessing={processingIds.has(competitor.id)}
            />
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <Pagination className="justify-center">
          <PaginationContent>
            <PaginationItem>
              {/* Paginação: anterior */}
              <PaginationPrevious
                href="#"
                onClick={(event) => {
                  event.preventDefault();
                  if (page > 1) {
                    handlePageChange(page - 1);
                  }
                }}
                aria-disabled={page === 1}
              />
            </PaginationItem>

            {Array.from({ length: totalPages }).map((_, index) => {
              const pageNumber = index + 1;
              return (
                <PaginationItem key={pageNumber}>
                  <PaginationLink
                    href="#"
                    isActive={pageNumber === page}
                    onClick={(event) => {
                      event.preventDefault();
                      handlePageChange(pageNumber);
                    }}
                  >
                    {pageNumber}
                  </PaginationLink>
                </PaginationItem>
              );
            })}

            <PaginationItem>
              {/* Paginação: próximo */}
              <PaginationNext
                href="#"
                onClick={(event) => {
                  event.preventDefault();
                  if (page < totalPages) {
                    handlePageChange(page + 1);
                  }
                }}
                aria-disabled={page === totalPages}
              />
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      )}
    </TabsContent>
  </Tabs>

  {/* Modal para adicionar concorrente: provê fallback de product enquanto carrega */}
  <AddCompetitorModal
    product={product ?? {
      id: productId,
      user_id: '',
      name_identification: 'Produto',
      monitoring_type: 'scraping',
      search_query: null,
      product_url: null,
      current_price: null,
      free_shipping: null,
      thumbnail: null,
      status: 'pending',
      last_checked: null,
      competitors_count: totalCompetitors,
      competitors_mean: null,
      competitors_min: null,
      competitors_max: null,
      position_rank: null,
      potential_savings: null,
      competitors_with_price_count: null,
      latest_comparison_id: null,
      last_comparison_at: null,
      is_new: false,
      comparison_insights: null,
    }}
    isOpen={isAddModalOpen}
    onClose={() => setIsAddModalOpen(false)}
    onScheduled={(_options) => {
      // Feedback otimista: fecha modal, informa usuário e recarrega dados
      toast.success('Concorrente enviado para coleta. Sincronizando lista...');
      setIsAddModalOpen(false);
      void loadCompetitors();
      void loadSummary();
    }}
  />
</div>

export default CompetitorsPage;
