/**
 * Utilitário para padronizar a exibição do preço monitorado em cards e tabelas.
 *
 * Centraliza os rótulos usados em estados especiais (indisponível, sem preço
 * ou coleta em andamento) para garantir consistência visual em páginas
 * diferentes.
 */
import React from 'react';
import { Typography } from '@mui/material';
import type { TypographyProps } from '@mui/material';
import { formatCurrency, normalizePriceInput } from './currency';
import { resolveMonitoredStatus } from './monitoredStatus';
import type { MonitoredProduct } from '../types';

interface RenderPriceOptions {
  variant?: TypographyProps['variant'];
  align?: TypographyProps['align'];
}

/**
 * Renderiza o valor monitorado com rótulos específicos para cada status.
 */
export const renderMonitoredPrice = (
  product: MonitoredProduct,
  options?: RenderPriceOptions,
) => {
  const parsed = normalizePriceInput(product.current_price);
  const status = resolveMonitoredStatus(product);
  const variant = options?.variant ?? 'h6';
  const align = options?.align;

  if (status === 'inactive') {
    return (
      <Typography variant={variant} color="text.secondary" align={align}>
        Indisponível
      </Typography>
    );
  }

  if (status === 'no_price') {
    return (
      <Typography variant={variant} color="text.secondary" align={align}>
        Sem preço
      </Typography>
    );
  }

  if (status === 'collecting') {
    return (
      <Typography variant={variant} color="text.secondary" align={align}>
        Coletando dados...
      </Typography>
    );
  }

  return (
    <Typography variant={variant} color="primary" align={align}>
      {formatCurrency(parsed, { fallbackLabel: 'Sem preço' })}
    </Typography>
  );
};
