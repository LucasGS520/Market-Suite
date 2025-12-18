/**
 * Badge reutilizável para exibir o status de monitoramento de um produto.
 * Encapsula a lógica de resolução de estado e tooltip para garantir consistência visual.
 */
import React from 'react';
import { Chip, Tooltip } from '@mui/material';
import type { MonitoredProduct } from '../types';
import { resolveMonitoredStatus, statusToBadge } from '../utils/monitoredStatus';

interface MonitoredStateBadgeProps {
  product: MonitoredProduct;
}

const MonitoredStateBadge: React.FC<MonitoredStateBadgeProps> = ({ product }) => {
  const status = resolveMonitoredStatus(product);
  const badge = statusToBadge[status] ?? statusToBadge.unknown;

  return (
    <Tooltip title={badge.tooltip} placement="top">
      <Chip
        label={badge.label}
        color={badge.color}
        size="small"
        aria-label={`Status de monitoramento: ${badge.label}`}
      />
    </Tooltip>
  );
};

export default MonitoredStateBadge;
