import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/data-display/card';
import { Badge } from '@/components/ui/data-display/badge';
import { Button } from '@/components/ui/button/button';
import { AlertCircle, ChevronDown, ChevronUp, Clock, ExternalLink, Loader2, RefreshCw, UserPlus, Users } from 'lucide-react';
import { cn, sanitizeExternalUrl } from '@/lib/utils';
import { MonitoredProduct, getCompetitors, Competitor, getComparisonSummary, ComparisonSummary } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { toast } from 'sonner';

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

/** Número padrão de concorrentes exibidos no modo expandido. */
const COMPETITOR_PREVIEW_COUNT = 3;

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
 * Descreve timestamps com validação básica.
 */
const describeTimestamp = (timestamp: string | null): string => {
  if (!timestamp) {
    return 'Nenhum registro disponível';
  }

  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return 'Data inválida';
  }

  return parsed.toLocaleString('pt-BR');
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
  const [comparisonSummary, setComparisonSummary] = useState<ComparisonSummary | null>(null);
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const summaryRequestTimeoutRef = useRef<number | null>(null);

  const statusDisplay = statusDisplayConfig[product.status];
  const detailsId = `monitored-${product.id}-details`;
  const competitorPreview = useMemo(
    () => competitors.slice(0, COMPETITOR_PREVIEW_COUNT),
    [competitors],
  );

  const remainingCompetitors = useMemo(() => {
    const total = product.competitors_count ?? competitors.length;
    const remaining = total - competitorPreview.length;
    return remaining > 0 ? remaining : 0;
  }, [competitorPreview.length, competitors.length, product.competitors_count]);

  const needsComparisonSummary = useMemo(
    () =>
      [
        product.average_competitor_price,
        product.min_competitor_price,
        product.max_competitor_price,
        product.position_rank,
      ].some((value) => value === null || value === undefined),
    [
      product.average_competitor_price,
      product.min_competitor_price,
      product.max_competitor_price,
      product.position_rank,
    ],
  );

  const mergedMetrics = useMemo(
    () => ({
      average: product.average_competitor_price ?? comparisonSummary?.average_competitor_price ?? null,
      min: product.min_competitor_price ?? comparisonSummary?.min_competitor_price ?? null,
      max: product.max_competitor_price ?? comparisonSummary?.max_competitor_price ?? null,
      position: product.position_rank ?? comparisonSummary?.position_rank ?? null,
      insights: product.comparison_insights ?? comparisonSummary?.comparison_insights ?? null,
    }),
    [
      product.average_competitor_price,
      product.min_competitor_price,
      product.max_competitor_price,
      product.position_rank,
      product.comparison_insights,
      comparisonSummary,
    ],
  );

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
   * Alterna a seção expandida carregando dados de concorrentes sob demanda.
   */
  const handleToggleExpand = async () => {
    const nextExpanded = !isExpanded;
    setIsExpanded(nextExpanded);

    if (nextExpanded && !hasLoadedCompetitorsRef.current) {
      await loadCompetitors();
    }
  };

  /**
   * Obtém resumo competitivo com debounce para evitar chamadas repetidas.
   */
  const fetchComparisonSummary = useCallback(async () => {
    if (!token) {
      return;
    }

    setIsLoadingSummary(true);
    setSummaryError(null);

    try {
      const summary = await getComparisonSummary(token, product.id);
      setComparisonSummary(summary);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Erro ao carregar resumo competitivo.';
      setSummaryError(message);
    } finally {
      setIsLoadingSummary(false);
    }
  }, [product.id, token]);

  /**
   * Permite nova tentativa manual quando o carregamento do resumo falha.
   */
  const handleRetrySummary = useCallback(() => {
    if (isLoadingSummary || !token) {
      return;
    }

    void fetchComparisonSummary();
  }, [fetchComparisonSummary, isLoadingSummary, token]);

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
    if (summaryRequestTimeoutRef.current !== null) {
      window.clearTimeout(summaryRequestTimeoutRef.current);
      summaryRequestTimeoutRef.current = null;
    }

    if (
      !isExpanded ||
      !needsComparisonSummary ||
      comparisonSummary !== null ||
      isLoadingSummary ||
      !token ||
      summaryError !== null
    ) {
      return;
    }

    summaryRequestTimeoutRef.current = window.setTimeout(() => {
      summaryRequestTimeoutRef.current = null;
      void fetchComparisonSummary();
    }, 300);

    return () => {
      if (summaryRequestTimeoutRef.current !== null) {
        window.clearTimeout(summaryRequestTimeoutRef.current);
        summaryRequestTimeoutRef.current = null;
      }
    };
  }, [
    comparisonSummary,
    fetchComparisonSummary,
    isExpanded,
    isLoadingSummary,
    needsComparisonSummary,
    summaryError,
    token,
  ]);

  useEffect(() => {
    setComparisonSummary(null);
    setSummaryError(null);
    setIsLoadingSummary(false);

    if (summaryRequestTimeoutRef.current !== null) {
      window.clearTimeout(summaryRequestTimeoutRef.current);
      summaryRequestTimeoutRef.current = null;
    }
  }, [product.id]);

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

  return (
    <Card
      className={cn(
        'relative transition-colors',
        statusDisplay.cardAccentClass,
      )}
    >
      {product.is_new && (
        <span className="bg-emerald-500/10 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-200 absolute right-6 top-6 rounded-full px-3 py-1 text-xs font-semibold">
          Novo
        </span>
      )}

      <CardHeader className="pb-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <CardTitle className="text-lg">
              {product.name_identification ?? 'Produto sem identificação'}
            </CardTitle>
            <CardDescription>
              Última atualização: {describeTimestamp(product.last_checked)}
            </CardDescription>
            {product.last_comparison_at && (
              <p className="text-xs text-muted-foreground">
                Última comparação: {describeTimestamp(product.last_comparison_at)}
              </p>
            )}
          </div>
          <div className="flex flex-col items-end gap-2">
            <Badge variant={statusDisplay.badgeVariant}>{statusDisplay.label}</Badge>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="text-xs text-muted-foreground">Seu preço</p>
            <p className="text-xl font-semibold">{formatCurrency(product.current_price)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Concorrentes monitorados</p>
            <div className="mt-1 flex items-center gap-2 text-sm">
              <Users className="h-4 w-4 text-muted-foreground" />
              <span className="text-base font-medium">
                {product.competitors_count ?? 0}
              </span>
            </div>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Preço médio concorrentes</p>
            <p className="text-lg font-medium">{formatCurrency(mergedMetrics.average)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Posição no ranking</p>
            <p className="text-lg font-medium">
              {mergedMetrics.position !== null && mergedMetrics.position > 0
                ? `#${mergedMetrics.position}`
                : 'Sem posição'}
            </p>
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
                <span>{summaryError}</span>
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
            <div className="grid gap-4 lg:grid-cols-3">
              <div>
                <p className="text-xs text-muted-foreground">Menor preço concorrente</p>
                <p className="text-sm font-medium">{formatCurrency(mergedMetrics.min)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Maior preço concorrente</p>
                <p className="text-sm font-medium">{formatCurrency(mergedMetrics.max)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Insight mais recente</p>
                <p className="text-sm">
                  {mergedMetrics.insights ?? 'Sem insights disponíveis no momento.'}
                </p>
              </div>
            </div>

            <div>
              <h3 className="text-sm font-semibold">Resumo de concorrentes</h3>
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
              {!isLoadingCompetitors && !competitorsError && competitorPreview.length === 0 && (
                <p className="mt-2 text-sm text-muted-foreground">Nenhum concorrente cadastrado até o momento.</p>
              )}
              {!isLoadingCompetitors && competitorPreview.length > 0 && (
                <ul className="mt-2 space-y-2">
                  {competitorPreview.map((competitor) => (
                    <li key={competitor.id} className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
                      <span className="mr-4 line-clamp-1 font-medium" title={competitor.name}>
                        {competitor.name}
                      </span>
                      <span className="text-muted-foreground">{formatCurrency(competitor.currentPrice)}</span>
                    </li>
                  ))}
                </ul>
              )}
              {remainingCompetitors > 0 && (
                <p className="mt-2 text-xs text-muted-foreground">
                  +{remainingCompetitors} concorrente(s) adicional(is) disponível(is) na lista completa.
                </p>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default MonitoredProductCard;
