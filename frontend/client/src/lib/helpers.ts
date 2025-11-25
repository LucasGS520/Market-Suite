/**
 * Utilitários compartilhados entre componentes da área de concorrentes.
 *
 * Mantém funções de formatação e mapeamentos que precisam ser reutilizados
 * em cards, tabelas e páginas, evitando duplicação e divergências.
 */

import { parseMoneyValue, formatMoney } from '@/lib/money';
import { sanitizeExternalUrl } from '@/lib/utils';
import type { Competitor } from '@/lib/api';

/**
 * Converte números ou strings monetárias em representação formatada no padrão brasileiro.
 */
export const formatCurrency = (value: number | string | null | undefined): string => {
  const parsed = parseMoneyValue(value ?? null);

  if (parsed === null || Number.isNaN(parsed)) {
    return 'Valor indisponível';
  }

  return formatMoney(parsed);
};

/**
 * Formata valores percentuais preservando duas casas decimais.
 * - Retorna hífen quando o valor for nulo ou inválido para facilitar leitura.
 */
export const formatPercentage = (value: number | null): string => {
  if (value === null || Number.isNaN(value)) {
    return '-';
  }

  return `${value.toFixed(2)}%`;
};

/**
 * Representa carimbo de data/hora relativo em português.
 * - Utilizado para exibir "há X dias" ou "em Y horas" na listagem.
 */
export const formatRelativeTime = (timestamp: string | null): string => {
  if (!timestamp) {
    return 'Sem registro';
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
 * Mapeia status técnicos de concorrentes para rótulos amigáveis.
 * - O tom auxilia na escolha de cores e ícones em cada card.
 */
export const statusDisplay: Record<
  Competitor['status'],
  { label: string; tone: 'positive' | 'neutral' | 'negative' }
> = {
  available: { label: 'Em estoque', tone: 'positive' },
  unavailable: { label: 'Indisponível', tone: 'neutral' },
  removed: { label: 'Removido', tone: 'negative' },
};

/**
 * Define classes utilitárias para destacar estados especiais em cards.
 * - Destaca itens pausados, indisponíveis ou removidos com cores distintas.
 */
export const resolveCardAccent = (competitor: Competitor): string => {
  if (competitor.is_paused) {
    return 'border-dashed border-slate-300 dark:border-slate-700 bg-muted/40';
  }

  if (competitor.status === 'removed') {
    return 'border-red-200 dark:border-red-900 bg-red-50/60 dark:bg-red-950/40';
  }

  if (competitor.status === 'unavailable') {
    return 'border-amber-200 dark:border-amber-800 bg-amber-50/60 dark:bg-amber-950/30';
  }

  return '';
};

/**
 * Sanitiza URLs externas de concorrentes antes de abrirmos em nova aba.
 * - Centraliza a regra para evitar espalhar `sanitizeExternalUrl` pelos componentes.
 */
export const resolveCompetitorUrl = (rawUrl: string | null): string | null => {
  if (!rawUrl) {
    return null;
  }

  return sanitizeExternalUrl(rawUrl);
};

export default {
  formatCurrency,
  formatPercentage,
  formatRelativeTime,
  statusDisplay,
  resolveCardAccent,
  resolveCompetitorUrl,
};