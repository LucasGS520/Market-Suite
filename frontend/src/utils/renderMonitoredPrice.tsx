/**
 * Utilitário para padronizar a exibição do preço monitorado em cards e tabelas.
 *
 * Centraliza os rótulos usados em estados especiais (indisponível, sem preço,
 * falha de coleta ou coleta em andamento) com mensagens acionáveis derivadas
 * diretamente do contrato semântico retornado pelo backend.
 */
import { Typography } from '@mui/material';
import type { TypographyProps } from '@mui/material';
import { formatCurrency, normalizePriceInput } from './currency';
import { formatRelativeTime } from './date';
import { resolveMonitoredStatus } from './productStatus';
import type { MonitoredProduct } from '../types';

interface RenderPriceOptions {
  variant?: TypographyProps['variant'];
  align?: TypographyProps['align'];
}

/**
 * Retorna a mensagem de estado de coleta contextual para cards e listas.
 * Usa a chave canônica do contrato para evitar heurísticas na UI.
 */
const resolveCollectionMessage = (product: MonitoredProduct): string | null => {
  const cs = product.collection_status;
  if (!cs) return null;

  const key = cs.collection_user_message_key;

  switch (key) {
    case 'collecting_real':
      return 'Coletando dados...';

    case 'retry_scheduled': {
      const retryAt = cs.collection_next_retry_at;
      const retryLabel = retryAt ? formatRelativeTime(retryAt) : null;
      return retryLabel
        ? `Falha temporária — nova tentativa ${retryLabel}`
        : 'Falha temporária — tentativa em andamento';
    }

    case 'failed_transient':
      return 'Falha temporária na coleta';

    case 'failed_structural':
      return 'Falha na coleta — verifique a URL';

    case 'domain_empty_no_price':
      return 'Sem preço disponível';

    case 'inactive_or_paused':
      return 'Monitoramento pausado';

    default:
      return null;
  }
};

/**
 * Renderiza o valor monitorado com rótulos específicos para cada status.
 * Prioriza mensagens do contrato de coleta quando disponíveis.
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

  // Estados de coleta com mensagem contratual
  if (
    status === 'collecting' ||
    status === 'retry_scheduled' ||
    status === 'error_transient' ||
    status === 'error_structural'
  ) {
    const contractMessage = resolveCollectionMessage(product);
    const message = contractMessage ?? 'Coletando dados...';
    const isError = status === 'error_structural';

    return (
      <Typography
        variant={variant}
        color={isError ? 'error' : 'text.secondary'}
        align={align}
      >
        {message}
      </Typography>
    );
  }

  return (
    <Typography variant={variant} color="primary" align={align}>
      {formatCurrency(parsed, { fallbackLabel: 'Sem preço' })}
    </Typography>
  );
};
