/**
 * Utilitários de data para formatações amigáveis na interface.
 */
export const formatRelativeTime = (iso?: string | null): string => {
  // Retorna marcador padrão quando não há valor ou data inválida
  if (!iso) return '—';
  const targetDate = new Date(iso);
  if (Number.isNaN(targetDate.getTime())) return '—';

  const now = new Date();
  const diffSeconds = Math.round((targetDate.getTime() - now.getTime()) / 1000);
  const absSeconds = Math.abs(diffSeconds);

  const formatter = new Intl.RelativeTimeFormat('pt-BR', { numeric: 'auto' });

  // Define faixas para escolher a unidade mais apropriada
  if (absSeconds < 60) {
    return formatter.format(diffSeconds, 'second');
  }

  const diffMinutes = Math.round(diffSeconds / 60);
  if (Math.abs(diffMinutes) < 60) {
    return formatter.format(diffMinutes, 'minute');
  }

  const diffHours = Math.round(diffMinutes / 60);
  if (Math.abs(diffHours) < 24) {
    return formatter.format(diffHours, 'hour');
  }

  const diffDays = Math.round(diffHours / 24);
  if (Math.abs(diffDays) < 7) {
    return formatter.format(diffDays, 'day');
  }

  const diffWeeks = Math.round(diffDays / 7);
  if (Math.abs(diffWeeks) < 4) {
    return formatter.format(diffWeeks, 'week');
  }

  const diffMonths = Math.round(diffWeeks / 4);
  if (Math.abs(diffMonths) < 12) {
    return formatter.format(diffMonths, 'month');
  }

  const diffYears = Math.round(diffMonths / 12);
  return formatter.format(diffYears, 'year');
};

/**
 * Converte uma string ISO em data local apenas, sem horário.
 */
export const formatDateOnly = (iso?: string | null): string => {
  // Garante retorno amigável em caso de ausência ou erro de parsing
  if (!iso) return '—';
  const parsedDate = new Date(iso);
  if (Number.isNaN(parsedDate.getTime())) return '—';

  return parsedDate.toLocaleDateString('pt-BR');
};
