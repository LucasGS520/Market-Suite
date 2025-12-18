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
  const availability = product.availability;
  const competitiveness =
    product.competitiveness_status || product.comparison_summary?.competitiveness_status;

  if (isPaused) return 'paused';
  if (availability === false) return 'inactive';

  if (availability === true && price === null && product.last_scraped_at) {
    return 'no_price';
  }

  if (!product.last_scraped_at && price === null) {
    return 'collecting';
  }

  if (competitiveness === 'competitivo') return 'competitive';
  if (competitiveness === 'atencao') return 'attention';
  if (competitiveness === 'urgente') return 'urgent';

  if (price === null) return 'unknown';
  return 'competitive';
};
