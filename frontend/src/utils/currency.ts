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
export function formatCurrency(
  value: CurrencyInput,
  { prefix = 'R$', fallbackLabel }: { prefix?: string; fallbackLabel?: string } = {},
): string {
  const fallback = fallbackLabel ?? (prefix ? `${prefix} 0,00` : '0,00');

  if (value === null || value === undefined) {
    return fallback;
  }

  const numericValue =
    typeof value === 'string'
      ? Number.parseFloat(value.replace(',', '.'))
      : Number(value);

  if (!Number.isFinite(numericValue)) {
    return fallback;
  }

  const formatted = numericValue.toFixed(2).replace('.', ',');
  return prefix ? `${prefix} ${formatted}` : formatted;
}
