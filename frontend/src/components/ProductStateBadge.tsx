/**
 * Badge reutilizável para exibir o status de monitoramento de produtos e concorrentes.
 * Centraliza resolução de status e tooltip para manter consistência visual entre itens.
 */
import React from 'react';
import { Chip, Tooltip } from '@mui/material';
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

const ProductStateBadge: React.FC<ProductStateBadgeProps> = ({ product, variant }) => {
  const resolvedVariant = variant || ('owner_id' in product ? 'monitored' : 'competitor');
  const status =
    resolvedVariant === 'monitored'
      ? resolveMonitoredStatus(product as MonitoredProduct)
      : resolveCompetitorStatus(product as CompetitorProduct);
  const badge = statusToBadge[status] ?? statusToBadge.unknown;

  return (
    <Tooltip title={badge.tooltip} placement="top">
      <Chip
        label={badge.label}
        color={badge.color}
        size="small"
        aria-label={`Status: ${badge.label}`}
      />
    </Tooltip>
  );
};

export default ProductStateBadge;
