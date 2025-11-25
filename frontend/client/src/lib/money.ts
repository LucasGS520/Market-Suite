import Decimal from 'decimal.js-light';

/**
 * Converte valores monetários em string ou number para number normalizado, preservando precisão com Decimal.
 */
export const parseMoneyValue = (value: string | number | null | undefined): number | null => {
  if (value === null || value === undefined || value === '') {
    return null;
  }

  try {
    const decimalValue = new Decimal(value);
    return decimalValue.toNumber();
  } catch (error) {
    console.warn('Valor monetário inválido recebido do backend.', value, error);
    return null;
  }
};

/**
 * Formata valores monetários para exibição com localização brasileira por padrão.
 */
export const formatMoney = (
  value: number | null | undefined,
  locale = 'pt-BR',
  currency = 'BRL',
): string => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }

  return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(value);
};
