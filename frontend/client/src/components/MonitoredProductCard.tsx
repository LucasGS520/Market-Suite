import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/data-display/card';
import { Badge } from '@/components/ui/data-display/badge';
import { Button } from '@/components/ui/button/button';
import { AlertCircle, ChevronDown, ChevronUp, Clock, ExternalLink, ImageOff, Loader2, RefreshCw, UserPlus, Users } from 'lucide-react';
import { cn, sanitizeExternalUrl } from '@/lib/utils';
import type { ComparisonSummary, Competitor, MonitoredProduct } from '@/lib/api';
import { getCompetitors } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { toast } from 'sonner';
import useComparisonSummary from '@/hooks/useComparisonSummary';

/**
 * Propriedades aceitas pelo cartão de produto monitorado.
 */
export interface MonitoredProductCardProps {
  product: MonitoredProduct;
  onViewCompetitors: () => void;
  onAddCompetitor: () => void;
  onRefresh: () => Promise<void>;
  isRefreshing: boolean;
  isRefreshingSelf: boolean;
}

/** Limite máximo de concorrentes exibidos em destaque no modo expandido. */
const COMPETITOR_HIGHLIGHT_COUNT = 2;

/**
 * Configuração visual dos status para badge e realce do cartão.
 */
const statusDisplayConfig: Record<
  MonitoredProduct['status'],
  {
    label: string;
    badgeVariant: 'default' | 'secondary' | 'destructive' | 'outline';
    cardAccentClass?: string;
  }
> = {
  active: { label: 'Ativo', badgeVariant: 'default' },
  inactive: { label: 'Inativo', badgeVariant: 'secondary' },
  pending: {
    label: 'Agendado',
    badgeVariant: 'outline',
    cardAccentClass: 'border-amber-300 bg-amber-50/60 dark:border-amber-500 dark:bg-amber-950/40',
  },
  failed: {
    label: 'Falha',
    badgeVariant: 'destructive',
    cardAccentClass: 'border-red-200 bg-red-50/60 dark:border-red-900 dark:bg-red-950/50',
  },
};

/**
 * Estrutura enxuta para exibir dados resumidos dos concorrentes.
 */
type CompetitorSummary = {
  id: string;
  name: string;
  currentPrice: number | null;
};

/**
 * Estrutura auxiliar para formatar a classificação competitiva.
 */
type CompetitiveDescriptor = {
  label: string;
  tone: 'positive' | 'neutral' | 'negative';
};

/**
 * Converte string/número potencialmente inválido em número ou ``null``.
 */
const toNumberOrNull = (value: string | number | null | undefined): number | null => {
  if (value === null || value === undefined) {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

/**
 * Formata valores monetários com fallback amigável.
 */
const formatCurrency = (value: number | null): string => {
  if (value === null || Number.isNaN(value)) {
    return 'Valor indisponível';
  }

  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: 2,
  }).format(value);
};

/**
 * Calcula descrição relativa do timestamp mais recente
 */
const formatRelativeTime = (timestamp: string | null): string => {
  if (!timestamp) {
    return 'Nenhum registro disponível';
  }

  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return 'Data inválida';
  }

    const now = Date.now();
  const diffInSeconds = Math.round((parsed.getTime() - now) / 1000);
  const absoluteSeconds = Math.abs(diffInSeconds);
  const formatter = new Intl.RelativeTimeFormat('pt-BR', { numeric: 'auto' });

  const thresholds: Array<{
    limit: number;
    divisor: number;
    unit: Intl.RelativeTimeFormatUnit;
  }> = [
    { limit: 60, divisor: 1, unit: 'second' },
    { limit: 3600, divisor: 60, unit: 'minute' },
    { limit: 86_400, divisor: 3600, unit: 'hour' },
    { limit: 604_800, divisor: 86_400, unit: 'day' },
    { limit: 2_629_800, divisor: 604_800, unit: 'week' },
    { limit: 31_557_600, divisor: 2_629_800, unit: 'month' },
    { limit: Number.POSITIVE_INFINITY, divisor: 31_557_600, unit: 'year' },
  ];

  for (const threshold of thresholds) {
    if (absoluteSeconds < threshold.limit) {
      const value = Math.round(diffInSeconds / threshold.divisor);
      return formatter.format(value, threshold.unit);
    }
  }

  return formatter.format(0, 'second');
};

/**
 * Extrai dados essenciais do concorrente retornado pela API.
 */
const mapCompetitorToSummary = (competitor: Competitor): CompetitorSummary => ({
  id: competitor.id,
  name: competitor.name_competitor,
  currentPrice: toNumberOrNull(competitor.current_price),
});

/**
 * Monta um resumo competitivo inicial a partir dos dados da listagem quando disponível.
 */
const buildInitialSummaryFromProduct = (product: MonitoredProduct): ComparisonSummary | undefined => {
  const hasSummaryData = [
    product.competitors_mean,
    product.competitors_min,
    product.competitors_max,
    product.position_rank,
    product.potential_savings,
    product.competitors_with_price_count,
    product.latest_comparison_id,
    product.last_comparison_at,
  ].some((value) => value !== null && value !== undefined);

  if (!hasSummaryData) {
    return undefined;
  }

  return {
    monitored_price: product.current_price,
    competitors_count: product.competitors_count ?? 0,
    competitors_with_price_count: product.competitors_with_price_count ?? product.competitors_count ?? 0,
    competitors_mean: product.competitors_mean,
    competitors_min: product.competitors_min,
    competitors_max: product.competitors_max,
    position_rank: product.position_rank,
    potential_savings: product.potential_savings,
    comparison_insights: product.comparison_insights ?? null,
    comparison_id: product.latest_comparison_id,
    last_comparison_at: product.last_comparison_at ?? null,
  };
};

/**
 * Constrói descrição textual para a posição no ranking competitivo.
 */
const describePosition = (
  summary: ComparisonSummary | null | undefined,
  fallbackCount: number | null,
): { shortLabel: string; detailedLabel: string } => {
  const totalCompetitors = summary?.competitors_with_price_count ?? fallbackCount ?? 0;
  const position = summary?.position_rank ?? null;

  if (!summary) {
    return {
      shortLabel: 'Sem resumo disponível',
      detailedLabel: 'Carregue os detalhes para visualizar o ranking competitivo.',
    };
  }

  if (!totalCompetitors || !position) {
    return {
      shortLabel: 'Ranking indisponível',
      detailedLabel: 'Aguardando preços válidos dos concorrentes para calcular a posição.',
    };
  }

  const ordinal = `${position}º`;
  const base = `${ordinal} mais barato de ${totalCompetitors}`;

  return {
    shortLabel: base,
    detailedLabel: `${base} concorrentes com preço válido.`,
  };
};

/**
 * Calcula mensagem e tonalidade para o potencial de ajuste.
 */
const describePotentialAdjustment = (summary: ComparisonSummary | null | undefined): {
  adjustmentLabel: string;
  competitiveness: CompetitivenessDescriptor;
} => {
  if (!summary) {
    return {
      adjustmentLabel: 'Resumo indisponível',
      competitiveness: { label: 'Clique em detalhes para carregar o resumo', tone: 'neutral' },
    };
  }

  if (!summary.competitors_with_price_count) {
    return {
      adjustmentLabel: 'Sem dados suficientes',
      competitiveness: { label: 'Aguardando concorrentes com preço válido', tone: 'neutral' },
    };
  }

  const potentialSavings = summary.potential_savings ?? 0;
  const absoluteSavings = Math.abs(potentialSavings);
  const formatted = formatCurrency(absoluteSavings);

  if (summary.potential_savings === null || summary.potential_savings <= 0) {
    return {
      adjustmentLabel: 'Nenhum ajuste necessário',
      competitiveness: { label: 'Competitivo', tone: 'positive' },
    };
  }

  return {
    adjustmentLabel: `Potencial ajuste: -${formatted}`,
    competitiveness: { label: 'Não competitivo', tone: 'negative' },
  };
};

/**
 * Seleciona concorrentes de destaque (menor e maior preço) entre os carregados.
 */
const buildCompetitorHighlights = (competitors: CompetitorSummary[]): CompetitorSummary[] => {
  const withPrice = competitors.filter((competitor) => competitor.currentPrice !== null);

  if (withPrice.length === 0) {
    return [];
  }

  const sorted = [...withPrice].sort((a, b) => (a.currentPrice! - b.currentPrice!));
  const highlights: CompetitorSummary[] = [];

  highlights.push(sorted[0]);

  const last = sorted[sorted.length - 1];
  if (last.id !== sorted[0].id) {
    highlights.push(last);
  }

  return highlights.slice(0, COMPETITOR_HIGHLIGHT_COUNT);
};

/**
 * Cartão responsável por apresentar o resumo e os detalhes de um produto monitorado.
 */
export const MonitoredProductCard: React.FC<MonitoredProductCardProps> = ({
  product,
  onViewCompetitors,
  onAddCompetitor,
  onRefresh,
  isRefreshing,
  isRefreshingSelf,
}) => {
  const { token } = useAuth();
  const [isExpanded, setIsExpanded] = useState(false);
  const [competitors, setCompetitors] = useState<CompetitorSummary[]>([]);
  const [isLoadingCompetitors, setIsLoadingCompetitors] = useState(false);
  const [competitorsError, setCompetitorsError] = useState<string | null>(null);
  const hasLoadedCompetitorsRef = useRef(false);
  const previousCompetitorCountRef = useRef<number | null>(product.competitors_count ?? null);
  const initialSummary = useMemo(() => buildInitialSummaryFromProduct(product), [product]);
  const {
    summary: summaryFromQuery,
    isLoading: isLoadingSummary,
    error: summaryError,
    hasAttemptedFetch,
    loadSummary,
    refetchSummary,
  } = useComparisonSummary(product.id, { initialSummary });

  const effectiveSummary = summaryFromQuery ?? initialSummary;
  const positionInfo = describePosition(effectiveSummary, product.competitors_count);
  const potentialInfo = describePotentialAdjustment(effectiveSummary);
  const competitorHighlights = useMemo(
    () => buildCompetitorHighlights(competitors),
    [competitors],
  );

  const statusDisplay = statusDisplayConfig[product.status];
  const detailsId = `monitored-${product.id}-details`;

  /**
   * Carrega concorrentes apenas quando necessário, evitando requisições redundantes.
   */
  const loadCompetitors = useCallback(async () => {
    if (!token) {
      return;
    }

    setIsLoadingCompetitors(true);
    setCompetitorsError(null);

    try {
      const response = await getCompetitors(token, product.id);
      const summary = response.map(mapCompetitorToSummary);
      setCompetitors(summary);
      hasLoadedCompetitorsRef.current = true;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao carregar concorrentes';
      setCompetitorsError(message);
      toast.error('Não foi possível carregar os concorrentes deste produto.');
    } finally {
      setIsLoadingCompetitors(false);
    }
  }, [product.id, token]);

  /**
   * Força tentativa de carregamento do resumo competitivo exibindo toast em caso de falha.
   */
  const ensureSummaryLoaded = useCallback(async () => {
    try {
      await loadSummary();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao carregar resumo competitivo.';
      toast.error(message);
    }
  }, [loadSummary]);

  /**
   * Alterna a seção expandida carregando dados adicionais sob demanda.
   */
  const handleToggleExpand = async () => {
    const nextExpanded = !isExpanded;
    setIsExpanded(nextExpanded);

    if (nextExpanded) {
      if (!hasLoadedCompetitorsRef.current) {
        await loadCompetitors();
      }
      if (initialSummary === undefined && summaryFromQuery === undefined && !summaryError) {
        await ensureSummaryLoaded();
      }
    }
  };

  /**
   * Permite nova tentativa manual quando o carregamento do resumo falha.
   */
  const handleRetrySummary = useCallback(async () => {
    try {
      await refetchSummary();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao carregar resumo competitivo.';
      toast.error(message);
    }
  }, [refetchSummary]);

  useEffect(() => {
    if (!isExpanded || !hasLoadedCompetitorsRef.current) {
      previousCompetitorCountRef.current = product.competitors_count ?? null;
      return;
    }

    const previous = previousCompetitorCountRef.current;
    const current = product.competitors_count ?? null;

    if (previous !== current) {
      previousCompetitorCountRef.current = current;
      hasLoadedCompetitorsRef.current = false;
      void loadCompetitors();
      return;
    }

    previousCompetitorCountRef.current = current;
  }, [isExpanded, loadCompetitors, product.competitors_count]);

  useEffect(() => {
    if (!isExpanded) {
      return;
    }

    if (initialSummary === undefined && summaryFromQuery === undefined && !summaryError && !isLoadingSummary) {
      void ensureSummaryLoaded();
    }
  }, [
    ensureSummaryLoaded,
    initialSummary,
    isExpanded,
    isLoadingSummary,
    summaryError,
    summaryFromQuery,
  ]);

  /**
   * Abre o anúncio sanitizando a URL para evitar execuções indevidas.
   */
  const handleOpenProductUrl = () => {
    const safeUrl = sanitizeExternalUrl(product.product_url);

    if (!safeUrl) {
      toast.error('URL do anúncio indisponível.');
      return;
    }

    window.open(safeUrl, '_blank', 'noopener');
  };

  /**
   * Encaminha a ação de atualização para o container evitando cliques repetidos.
   */
  const handleRefresh = async () => {
    if (isRefreshing) {
      return;
    }

    try {
      await onRefresh();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro ao atualizar produtos';
      toast.error(message);
    }
  };

  const summaryUnavailable = 
    effectiveSummary === undefined && !isLoadingSummary && !summaryError && !hasAttemptedFetch;

  return (
    <Card
      className={cn(
        'relative overflow-hidden transition-colors',
        statusDisplay.cardAccentClass,
      )}
    >
      {product.is_new && product.status === 'pending' && (
        <span className="bg-emerald-500/10 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-200 absolute right-6 top-6 rounded-full px-3 py-1 text-xs font-semibold">
          Novo
        </span>
      )}

      <CardHeader className="pb-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex gap-4">
            <div className="bg-muted flex h-16 w-16 items-center justify-center overflow-hidden rounded-md border">
              {product.thumbnail ? (
                <img
                  src={product.thumbnail}
                  alt={product.name_identification ?? 'Produto monitorado'}
                  className="h-full w-full object-cover"
                  loading="lazy"
                />
              ) : (
                <ImageOff className="h-6 w-6 text-muted-foreground" />
              )}
            </div>
            <div className="space-y-1">
              <CardTitle className="text-lg">
                {product.name_identification ?? 'Produto sem identificação'}
              </CardTitle>
              <CardDescription>
                Última coleta: {formatRelativeTime(product.last_checked)}
              </CardDescription>
              {effectiveSummary?.last_comparison_at && (
                <p className="text-xs text-muted-foreground">
                  Última comparação: {formatRelativeTime(effectiveSummary.last_comparison_at)}
                </p>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <Badge variant={statusDisplay.badgeVariant}>{statusDisplay.label}</Badge>
            <span className="text-xs text-muted-foreground">
              Concorrentes monitorados: {product.competitors_count ?? 0}
            </span>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="grid gap-4 md:grid-cols-4">
          <div>
            <p className="text-xs text-muted-foreground">Seu preço</p>
            <p className="text-xl font-semibold">{formatCurrency(product.current_price)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Média dos concorrentes</p>
            <p className="text-lg font-medium">
              {effectiveSummary ? formatCurrency(effectiveSummary.competitors_mean) : 'Disponível nos detalhes'}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Posição resumida</p>
            <p className="text-lg font-medium">{positionInfo.shortLabel}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Estado competitivo</p>
            <span
              className={cn(
                'inline-flex items-center rounded-full px-3 py-1 text-sm font-medium',
                potentialInfo.competitiveness.tone === 'positive' &&
                  'bg-emerald-500/10 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-100',
                potentialInfo.competitiveness.tone === 'negative' &&
                  'bg-red-500/10 text-red-700 dark:bg-red-500/20 dark:text-red-200',
                potentialInfo.competitiveness.tone === 'neutral' && 'bg-muted text-muted-foreground',
              )}
            >
              {potentialInfo.competitiveness.label}
            </span>
          </div>
        </div>

        <div className="grid gap-3 text-sm md:grid-cols-2">
          <div className="rounded-md border border-dashed p-3">
            <p className="text-xs text-muted-foreground">Resumo de ajuste</p>
            <p>{potentialInfo.adjustmentLabel}</p>
          </div>
          <div className="rounded-md border border-dashed p-3">
            <p className="text-xs text-muted-foreground">Insight recente</p>
            <p>{effectiveSummary?.comparison_insights ?? 'Nenhum insight registrado ainda.'}</p>
          </div>
        </div>

        {product.status === 'pending' && (
          <div className="border-amber-200 bg-amber-50/80 text-amber-800 dark:border-amber-600 dark:bg-amber-950/40 dark:text-amber-200 flex items-center gap-2 rounded-md border border-dashed p-3 text-sm">
            <Clock className="h-4 w-4" />
            Coleta inicial agendada. Atualize em alguns minutos para acompanhar os preços.
          </div>
        )}
        {product.status === 'failed' && (
          <div className="border-red-200 bg-red-50/80 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300 flex items-center gap-2 rounded-md border p-3 text-sm">
            <AlertCircle className="h-4 w-4" />
            Última coleta falhou. Utilize a ação de atualizar para tentar novamente.
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleToggleExpand}
            aria-expanded={isExpanded}
            aria-controls={detailsId}
            className="gap-2"
          >
            {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            {isExpanded ? 'Ocultar detalhes' : 'Ver detalhes'}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleOpenProductUrl}
            disabled={!sanitizeExternalUrl(product.product_url)}
            className="gap-2"
          >
            <ExternalLink className="h-4 w-4" />
            Ver anúncio
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={handleRefresh}
            disabled={isRefreshing}
          >
            <RefreshCw className={cn('h-4 w-4', isRefreshingSelf && 'animate-spin')} />
            Atualizar
          </Button>
          <Button
            type="button"
            size="sm"
            className="gap-2"
            onClick={onAddCompetitor}
          >
            <UserPlus className="h-4 w-4" />
            Adicionar concorrente
          </Button>
          <Button type="button" variant="outline" size="sm" className="gap-2" onClick={onViewCompetitors}>
            <Users className="h-4 w-4" />
            Ver concorrentes
          </Button>
        </div>

        {summaryUnavailable && (
          <div className="rounded-md border border-dashed border-muted-foreground/40 bg-muted/40 p-3 text-sm text-muted-foreground">
            Expanda o cartão para carregar o resumo competitivo mais recente.
          </div>
        )}

        {isExpanded && (
          <div className="space-y-4 border-t pt-4" id={detailsId}>
            {isLoadingSummary && (
              <div className="flex items-center gap-2 rounded-md border border-dashed border-muted-foreground/40 bg-muted/40 p-3 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Carregando resumo competitivo...
              </div>
            )}
            {summaryError && (
              <div className="flex flex-wrap items-center gap-2 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
                <AlertCircle className="h-4 w-4" />
                <span>{summaryError.message}</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="ml-auto"
                  onClick={handleRetrySummary}
                  disabled={isLoadingSummary}
                >
                  Tentar novamente
                </Button>
              </div>
            )}
            {effectiveSummary && (
              <>
                <div className="grid gap-4 lg:grid-cols-4">
                  <div className="rounded-md border p-3">
                    <p className="text-xs text-muted-foreground">Preço monitorado</p>
                    <p className="text-sm font-medium">{formatCurrency(effectiveSummary.monitored_price ?? product.current_price)}</p>
                  </div>
                  <div className="rounded-md border p-3">
                    <p className="text-xs text-muted-foreground">Média dos concorrentes</p>
                    <p className="text-sm font-medium">{formatCurrency(effectiveSummary.competitors_mean)}</p>
                  </div>
                  <div className="rounded-md border p-3">
                    <p className="text-xs text-muted-foreground">Faixa de preços</p>
                    <p className="text-sm font-medium">
                      {`${formatCurrency(effectiveSummary.competitors_min)} — ${formatCurrency(effectiveSummary.competitors_max)}`}
                    </p>
                  </div>
                  <div className="rounded-md border p-3">
                    <p className="text-xs text-muted-foreground">Posição detalhada</p>
                    <p className="text-sm font-medium">{positionInfo.detailedLabel}</p>
                  </div>
                </div>

                <div className="rounded-md border border-dashed p-3 text-sm">
                  <p className="text-xs text-muted-foreground">Insights</p>
                  <p>{effectiveSummary.comparison_insights ?? 'Nenhum insight registrado ainda.'}</p>
                </div>
              </>
            )}

            {!isLoadingSummary && !summaryError && !effectiveSummary && (
              <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
                Resumo competitivo ainda não disponível. Execute uma coleta para gerar novos dados.
              </div>
            )}

            <div>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">Concorrentes em destaque</h3>
                <span className="text-xs text-muted-foreground">
                  {product.competitors_with_price_count ?? product.competitors_count ?? 0} com preço válido
                </span>
              </div>
              {isLoadingCompetitors && (
                <div className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Carregando lista de concorrentes...
                </div>
              )}
              {competitorsError && (
                <div className="mt-2 flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                  <AlertCircle className="h-4 w-4" />
                  {competitorsError}
                </div>
              )}
              {!isLoadingCompetitors && !competitorsError && competitorHighlights.length === 0 && (
                <p className="mt-2 text-sm text-muted-foreground">Nenhum concorrente com preço disponível no momento.</p>
              )}
              {!isLoadingCompetitors && competitorHighlights.length > 0 && (
                <ul className="mt-2 space-y-2">
                  {competitorHighlights.map((competitor) => (
                    <li key={competitor.id} className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
                      <span className="mr-4 line-clamp-1 font-medium" title={competitor.name}>
                        {competitor.name}
                      </span>
                      <span className="text-muted-foreground">{formatCurrency(competitor.currentPrice)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default MonitoredProductCard;
