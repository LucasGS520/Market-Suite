/**
 * Utilitário para resolver estado de monitoramento de produtos e mapear badges de UI.
 * Centraliza as regras de prioridade entre disponibilidade, pausa manual e competitividade,
 * retornando rótulos, cores e dicas contextuais em português.
 */
import type { ChipProps } from '@mui/material';
import { normalizePriceInput } from './currency';
import type { CompetitorProduct, MonitoredProduct } from '../types';

export type MonitoredStatusKey =
  | 'inactive'
  | 'paused'
  | 'no_price'
  | 'active'
  | 'competitive'
  | 'attention'
  | 'urgent'
  | 'no_competitors'
  | 'collecting'
  | 'retry_scheduled'
  | 'error_transient'
  | 'error_structural'
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
  active: {
    label: 'Disponível',
    color: 'success',
    tooltip: 'Concorrente disponível e apto para comparação.',
  },
  unknown: {
    label: 'Sem status',
    color: 'default',
    tooltip: 'Status não identificado ou aguardando atualização.',
  },
  retry_scheduled: {
    label: 'Aguardando',
    color: 'warning',
    tooltip: 'Falha temporária. Nova tentativa automática agendada.',
  },
  error_transient: {
    label: 'Falha Temp.',
    color: 'warning',
    tooltip: 'Falha técnica temporária na coleta. Sistema tentará novamente.',
  },
  error_structural: {
    label: 'Falha Coleta',
    color: 'error',
    tooltip: 'A estrutura da página mudou ou a URL é inválida. Verifique o produto.',
  },
};

/**
 * Mapeia a chave canônica de mensagem de coleta para o MonitoredStatusKey correspondente.
 * Usado quando display_status_priority === 'collection_status'.
 */
const collectionMsgKeyToStatus: Record<string, MonitoredStatusKey> = {
  collecting_real: 'collecting',
  retry_scheduled: 'retry_scheduled',
  failed_transient: 'error_transient',
  failed_structural: 'error_structural',
  domain_empty_no_price: 'no_price',
  inactive_or_paused: 'paused',
};

/**
 * Resolve o estado do produto monitorado priorizando pausa e disponibilidade.
 *
 * Ordem de prioridade:
 * 1. Indisponibilidade / pausa explícita (maior prioridade — sempre exibida).
 * 2. display_status_priority contratual:
 *    - 'collection_status': usa collection_user_message_key para determinar o status.
 *    - 'display_status': usa display_status retornado pelo backend.
 *    - null: produto sem coleta registrada → 'collecting'.
 * 3. Fallback heurístico para produtos sem o campo display_status_priority
 *    (retrocompatibilidade com respostas de API sem o contrato v1).
 */
export const resolveMonitoredStatus = (product: MonitoredProduct): MonitoredStatusKey => {
  const price = normalizePriceInput(product.current_price);
  const isPaused = product.is_paused ?? product.paused ?? false;
  const availability = product.availability as boolean | undefined;
  const competitiveness = product.competitiveness_status || product.comparison_summary?.competitiveness_status;
  const lastStatus = product.last_status;
  const displayStatus = product.display_status;

  const competitorsWithPrice =
    product.comparison_summary?.competitors_with_price_count ??
    product.comparison_summary?.competitors_count ??
    0;

  // ── 1. Indisponibilidade e pausa — sempre têm prioridade ──────────────────
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

  // ── 2. Lógica contratual (display_status_priority presente na resposta) ────
  if ('display_status_priority' in product) {
    const priority = product.display_status_priority;

    // Sem estado de coleta registrado → produto em primeira coleta real
    if (priority === null || priority === undefined) {
      return 'collecting';
    }

    if (priority === 'collection_status') {
      const msgKey = product.collection_status?.collection_user_message_key ?? null;
      if (msgKey && msgKey in collectionMsgKeyToStatus) {
        return collectionMsgKeyToStatus[msgKey];
      }
      // Fallback dentro do contrato: estado de coleta desconhecido → 'collecting'
      return 'collecting';
    }

    // priority === 'display_status': usa status consolidado do backend
    if (displayStatus) {
      if (['competitive', 'attention', 'urgent'].includes(displayStatus)) {
        if (competitorsWithPrice <= 0) return 'no_competitors';
      }
      return displayStatus as MonitoredStatusKey;
    }
  }

  // ── 3. Fallback heurístico (retrocompatibilidade sem display_status_priority) ──
  if (displayStatus) {
    if (['competitive', 'attention', 'urgent'].includes(displayStatus)) {
      if (competitorsWithPrice <= 0) return 'no_competitors';
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

/**
 * Resolve status de concorrentes para manter badge coerente com indisponibilidade e pausa.
 */
export const resolveCompetitorStatus = (
  competitor: CompetitorProduct
): MonitoredStatusKey => {
  const availability = competitor.availability;
  const isPaused = competitor.is_paused ?? false;
  const price = normalizePriceInput(competitor.current_price);

  if (availability === false) return 'inactive';

  if (isPaused) return 'paused';

  if (!competitor.last_scraped_at && price === null) return 'collecting';

  if (availability === true && price === null) return 'no_price';

  return price === null ? 'unknown' : 'active';
};
