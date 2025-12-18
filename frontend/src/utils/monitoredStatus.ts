/**
 * Utilitário para resolver estado de monitoramento de produtos e mapear badges de UI.
 * Centraliza as regras de prioridade entre disponibilidade, pausa manual e competitividade,
 * retornando rótulos, cores e dicas contextuais em português.
 */
import type { ChipProps } from '@mui/material';
import { normalizePriceInput } from './currency';
import type { MonitoredProduct } from '../types';

export type MonitoredStatusKey =
  | 'inactive'
  | 'paused'
  | 'no_price'
  | 'competitive'
  | 'attention'
  | 'urgent'
  | 'no_competitors'
  | 'collecting'
  | 'unknown';

interface MonitoredBadgeMeta {
  label: string;
  color: ChipProps['color'];
  tooltip: string;
}

/**
 * Mapeamento de status para rótulos, cor do Chip do MUI e tooltip auxiliar.
 */
export const statusToBadge: Record<MonitoredStatusKey, MonitoredBadgeMeta> = {
  inactive: {
    label: 'Inativo',
    color: 'default',
    tooltip: 'Produto indisponível no site de origem.',
  },
  paused: {
    label: 'Pausado',
    color: 'default',
    tooltip: 'Monitoramento pausado manualmente.',
  },
  no_price: {
    label: 'Sem preço',
    color: 'warning',
    tooltip: 'Disponível, mas sem preço identificado na última coleta.',
  },
  competitive: {
    label: 'Competitivo',
    color: 'success',
    tooltip: 'Preço dentro do patamar competitivo frente aos concorrentes.',
  },
  attention: {
    label: 'Atenção',
    color: 'warning',
    tooltip: 'Requer revisão: concorrência pode estar mais atrativa.',
  },
  urgent: {
    label: 'Urgente',
    color: 'error',
    tooltip: 'Necessita ação rápida para recuperar competitividade.',
  },
  no_competitors: {
    label: 'Sem concorrentes',
    color: 'default',
    tooltip: 'Nenhum concorrente com preço disponível.',
  },
  collecting: {
    label: 'Coletando',
    color: 'default',
    tooltip: 'Primeira coleta em andamento ou dados ainda não consolidados.',
  },
  unknown: {
    label: 'Sem status',
    color: 'default',
    tooltip: 'Status não identificado ou aguardando atualização.',
  },
};

/**
 * Resolve o estado do produto monitorado priorizando pausa e disponibilidade.
 * Usa o status de competitividade apenas quando o item está ativo e com coleta.
 */
export const resolveMonitoredStatus = (product: MonitoredProduct): MonitoredStatusKey => {
  const price = normalizePriceInput(product.current_price);
  const isPaused = product.is_paused ?? false;
  const availability = product.availability as boolean | undefined;
  const competitiveness = product.competitiveness_status || product.comparison_summary?.competitiveness_status;
  const lastStatus = product.last_status;
  const displayStatus = product.display_status;

  const competitorsWithPrice =
    product.comparison_summary?.competitors_with_price_count ??
    product.comparison_summary?.competitors_count ??
    0;

  if (product.comparison_summary?.ignored_due_to_inactive) {
    return 'inactive';
  }

  if (availability === false) return 'inactive';
  if (lastStatus) {
    const normalized = lastStatus
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, ' ')
      .trim();

    const unavailableSignals = [
      'indisponivel',
      'sem estoque',
      'sold out',
      'soldout',
      'sold_out',
      'no stock',
      'removed',
      'unavailable',
    ];

    if (unavailableSignals.some((signal) => normalized.includes(signal))) {
      return 'inactive';
    }
  }

  if (isPaused) return 'paused';

  if (displayStatus) {
    if (['competitive', 'attention', 'urgent'].includes(displayStatus)) {
      if (competitorsWithPrice <= 0) return 'no_competitors';
      if (availability === false) return 'inactive';
    }
    return displayStatus as MonitoredStatusKey;
  }

  if (!product.last_scraped_at && price === null) {
    return 'collecting';
  }

  if (availability === true && price === null && product.last_scraped_at) {
    return 'no_price';
  }

  if (competitorsWithPrice === 0) {
    return 'no_competitors';
  }

  if (competitiveness === 'competitivo') return 'competitive';
  if (competitiveness === 'atencao') return 'attention';
  if (competitiveness === 'urgente') return 'urgent';

  if (price === null) return 'unknown';
  return 'competitive';
};
