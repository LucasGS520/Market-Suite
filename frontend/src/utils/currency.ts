/**
 * Utilitários de formatação monetária para exibição no frontend.
 *
 * Centraliza a coerção de valores recebidos da API (string, number ou nulos)
 * para minimizar erros de renderização quando o backend retorna strings para
 * campos monetários e garantir consistência na exibição.
 */
export type CurrencyInput = number | string | null | undefined;

/**
 * Converte valores diversos em string monetária sempre segura para renderização.
 *
 * Se o valor não puder ser convertido para número finito, retorna o fallback
 * informado. A função também troca vírgulas por pontos para aceitar formatos
 * comuns em respostas serializadas como string.
 */
export function normalizePriceInput(value: CurrencyInput, { allowZero = false } = {}): number | null {
  /**
   * Normaliza entradas de preço retornando ``null`` quando inválidas ou zeradas.
   *
   * Converte strings, números ou valores nulos em um número pronto para
   * formatação, descartando ocorrências com valor ``0`` para evitar exibir
   * "R$ 0,00" na interface, com opção para permitir zeros em cenários de
   * diferença ou ajustes.
   */
  if (value === null || value === undefined) {
    return null;
  }

  const numericValue =
    typeof value === 'string'
      ? Number.parseFloat(value.replace(',', '.'))
      : Number(value);

  if (!Number.isFinite(numericValue)) {
    return null;
  }

  if (numericValue === 0 && !allowZero) {
    return null;
  }

  return numericValue;
}

export function formatCurrency(
  value: CurrencyInput,
  { prefix = 'R$', fallbackLabel = 'Indisponível / Pausado', allowZero = false }: {
    prefix?: string;
    fallbackLabel?: string;
    allowZero?: boolean;
  } = {},
): string {
  const normalized = normalizePriceInput(value, { allowZero: allowZero ?? false });
  if (normalized === null) {
    return fallbackLabel;
  }

  const formatted = normalized.toFixed(2).replace('.', ',');
  return prefix ? `${prefix} ${formatted}` : formatted;
}
