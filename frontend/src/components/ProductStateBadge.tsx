/**
 * Badge reutilizável para exibir o status de monitoramento de produtos e concorrentes.
 * Centraliza resolução de status e tooltip para manter consistência visual entre itens.
 */
import React from 'react';
import { Chip, Tooltip } from '@mui/material';
import type { ChipProps } from '@mui/material';
import type { CompetitorProduct, MonitoredProduct } from '../types';
import {
  resolveCompetitorStatus,
  resolveMonitoredStatus,
  statusToBadge,
} from '../utils/productStatus';

interface ProductStateBadgeProps {
  product: MonitoredProduct | CompetitorProduct;
  variant?: 'monitored' | 'competitor';
}

// Mapeamento de cores MUI → tokens semânticos do design system
const chipSxByColor: Record<NonNullable<ChipProps['color']>, object> = {
  success: {
    color: 'var(--color-semantic-success)',
    backgroundColor: 'var(--color-semantic-success-bg)',
    border: 'none',
  },
  warning: {
    color: 'var(--color-semantic-warning)',
    backgroundColor: 'var(--color-semantic-warning-bg)',
    border: 'none',
  },
  error: {
    color: 'var(--color-semantic-danger)',
    backgroundColor: 'var(--color-semantic-danger-bg)',
    border: 'none',
  },
  info: {
    color: 'var(--color-semantic-info)',
    backgroundColor: 'var(--color-semantic-info-bg)',
    border: 'none',
  },
  default: {
    color: 'var(--color-text-muted)',
    backgroundColor: 'rgba(255,255,255,0.06)',
    border: 'none',
  },
  primary: {
    color: 'var(--color-accent-primary)',
    backgroundColor: 'var(--color-surface-active)',
    border: 'none',
  },
  secondary: {
    color: 'var(--color-text-inverse)',
    backgroundColor: 'var(--color-accent-secondary)',
    border: 'none',
  },
};

const ProductStateBadge: React.FC<ProductStateBadgeProps> = ({ product, variant }) => {
  const resolvedVariant = variant || ('owner_id' in product ? 'monitored' : 'competitor');
  const status =
    resolvedVariant === 'monitored'
      ? resolveMonitoredStatus(product as MonitoredProduct)
      : resolveCompetitorStatus(product as CompetitorProduct);
  const badge = statusToBadge[status] ?? statusToBadge.unknown;
  const isPaused = status === 'paused';
  const pausedTooltip =
    resolvedVariant === 'monitored'
      ? 'Monitoramento pausado. Ações de concorrentes estão bloqueadas até a retomada.'
      : badge.tooltip;
  const tooltipText = isPaused ? pausedTooltip : badge.tooltip;

  const colorKey = (badge.color ?? 'default') as NonNullable<ChipProps['color']>;
  const colorSx = chipSxByColor[colorKey] ?? chipSxByColor.default;

  return (
    <Tooltip title={tooltipText} placement="top">
      <Chip
        label={badge.label}
        size="small"
        variant="filled"
        className="badge-enter"
        aria-label={`Status: ${badge.label}`}
        sx={{
          ...colorSx,
          ...(isPaused && {
            backgroundColor: 'transparent',
            border: '1px dashed var(--color-border-default)',
          }),
          fontWeight: 500,
          fontSize: '0.75rem',
          borderRadius: 'var(--radius-sm)',
          height: '20px',
          '& .MuiChip-label': { px: 1 },
        }}
      />
    </Tooltip>
  );
};

export default ProductStateBadge;
