/**
 * Componente responsável por apresentar dados e ações de um concorrente específico.
 *
 * - Utiliza abordagem card-first para destacar preço e disponibilidade.
 * - Oferece ações locais (pausar, retomar, remover) sem acoplar regras externas.
 */

import React, { useCallback } from 'react';
import { toast } from 'sonner';
import { ExternalLink, Loader2, Pause, Play, Slash, TrendingDown, TrendingUp, Trash2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/data-display/card';
import { Badge } from '@/components/ui/data-display/badge';
import { Button } from '@/components/ui/button/button';
import { Checkbox } from '@/components/ui/inputs/checkbox';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/overlay/alert-dialog';
import type { Competitor } from '@/lib/api';
import { formatCurrency, formatPercentage, formatRelativeTime, resolveCardAccent, resolveCompetitorUrl, statusDisplay } from '@/lib/helpers';

/**
 * Propriedades aceitas pelo componente de card de concorrente.
 */
export interface CompetitorCardProps {
  competitor: Competitor;
  isSelected: boolean;
  onToggleSelection: (id: string) => void;
  onPause: (id: string) => Promise<void>;
  onResume: (id: string) => Promise<void>;
  onRemove: (id: string) => Promise<void>;
  isProcessing: boolean;
}

/**
 * Card individual de concorrente com botões de ação e indicadores de tendência.
 */
export const CompetitorCard: React.FC<CompetitorCardProps> = ({
  competitor,
  isSelected,
  onToggleSelection,
  onPause,
  onResume,
  onRemove,
  isProcessing,
}) => {
  const trendValue = competitor.price_change ?? 0;
  const trendPercentage = competitor.price_change_percentage ?? null;
  const isPriceDown = trendValue < 0;
  const isPriceUp = trendValue > 0;

  /**
   * Abre o anúncio do concorrente em nova aba após sanitizar a URL.
   */
  const handleOpenLink = useCallback(() => {
    const sanitizedUrl = resolveCompetitorUrl(competitor.product_url);

    if (!sanitizedUrl) {
      toast.error('Não foi possível abrir o anúncio. Verifique a URL cadastrada.');
      return;
    }

    window.open(sanitizedUrl, '_blank', 'noopener,noreferrer');
  }, [competitor.product_url]);

  return (
    <Card className={`transition-colors ${resolveCardAccent(competitor)}`}>
      <CardHeader className="flex flex-col gap-2 pb-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          {/* Checkbox para seleção individual do concorrente */}
          <Checkbox
            checked={isSelected}
            onCheckedChange={() => onToggleSelection(competitor.id)}
            aria-label={`Selecionar concorrente ${competitor.name}`}
            className="mt-1"
          />
          <div>
            <CardTitle className="text-lg font-semibold">{competitor.name}</CardTitle>
            <CardDescription>
              Última coleta: {formatRelativeTime(competitor.last_checked)}
            </CardDescription>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {competitor.is_paused && <Badge variant="outline">Pausado</Badge>}
          <Badge>{statusDisplay[competitor.status].label}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="text-xs text-muted-foreground">Preço atual</p>
            <p className="text-xl font-semibold">{formatCurrency(competitor.current_price)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Preço anterior</p>
            <p className="text-xl font-semibold">{formatCurrency(competitor.previous_price)}</p>
          </div>
          <div className="flex items-center gap-2">
            {isPriceDown && <TrendingDown className="h-5 w-5 text-emerald-600" />}
            {isPriceUp && <TrendingUp className="h-5 w-5 text-red-500" />}
            {!isPriceDown && !isPriceUp && <Slash className="h-5 w-5 text-muted-foreground" />}
            <div>
              <p className="text-xs text-muted-foreground">Variação</p>
              <p className="text-sm font-medium">
                {formatCurrency(trendValue !== 0 ? Math.abs(trendValue) : null)}{' '}
                {trendValue !== 0 && (
                  <span className={isPriceDown ? 'text-emerald-600' : 'text-red-500'}>
                    ({formatPercentage(trendPercentage ? Math.abs(trendPercentage) : null)})
                  </span>
                )}
              </p>
            </div>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Disponibilidade</p>
            <p className="text-sm font-medium capitalize">
              {competitor.is_paused ? 'Monitoramento pausado' : statusDisplay[competitor.status].label}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {/* Botão para abrir anúncio em nova aba (URL sanitizada) */}
          <Button
            type="button"
            variant="outline"
            className="gap-2"
            disabled={!competitor.product_url}
            onClick={handleOpenLink}
          >
            <ExternalLink className="h-4 w-4" /> Ver anúncio
          </Button>

          {/* Botão para pausar monitoramento do concorrente (mostra loading no item) */}
          {!competitor.is_paused ? (
            <Button
              type="button"
              variant="secondary"
              className="gap-2"
              disabled={isProcessing}
              onClick={() => onPause(competitor.id)}
            >
              {isProcessing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Pause className="h-4 w-4" />}
              Pausar
            </Button>
          ) : (
            /* Botão para retomar monitoramento do concorrente (mostra loading no item) */
            <Button
              type="button"
              variant="secondary"
              className="gap-2"
              disabled={isProcessing}
              onClick={() => onResume(competitor.id)}
            >
              {isProcessing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              Retomar
            </Button>
          )}

          {/* Diálogo de confirmação para remoção (ação irreversível) */}
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button type="button" variant="destructive" className="gap-2" disabled={isProcessing}>
                {isProcessing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />} Remover
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Remover concorrente</AlertDialogTitle>
                <AlertDialogDescription>
                  A remoção é definitiva e fará com que os dados históricos sejam descartados.
                  Deseja continuar?
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancelar</AlertDialogCancel>
                <AlertDialogAction onClick={() => onRemove(competitor.id)}>Remover</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </CardContent>
    </Card>
  );
};

export default CompetitorCard;