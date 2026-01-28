/**
 * Utilitários de data para formatações amigáveis na interface.
 */

const parseIsoAsUtc = (iso?: string | null): Date | null => {
  if (!iso) return null;
  const trimmed = iso.trim();
  if (!trimmed) return null;

  // Assume UTC quando o backend não envia offset explícito para preservar coerência
  const normalized = /[zZ]|[+-]\d{2}:?\d{2}$/.test(trimmed) ? trimmed : `${trimmed}Z`;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

export const formatRelativeTime = (iso?: string | null): string => {
  // Retorna marcador padrão quando não há valor ou data inválida
  const targetDate = parseIsoAsUtc(iso);
  if (!targetDate) return '—';

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
 * Formata a data da última mudança de preço de forma profissional.
 * Exibe apenas o tempo relativo de forma clara (minutos, horas, dias, meses).
 * Evita termos informais como "ontem" ou "anteontem".
 */
export const formatLastPriceChangeDate = (iso?: string | null): string => {
  const targetDate = parseIsoAsUtc(iso);
  if (!targetDate) return '—';

  const now = new Date();
  const diffSeconds = Math.round((now.getTime() - targetDate.getTime()) / 1000);
  const absSeconds = Math.abs(diffSeconds);

  // Para mudanças muito recentes
  if (absSeconds < 60) {
    return 'Agora há pouco';
  }

  const diffMinutes = Math.round(diffSeconds / 60);
  if (Math.abs(diffMinutes) < 60) {
    const mins = Math.abs(diffMinutes);
    return `${mins} ${mins === 1 ? 'minuto' : 'minutos'} atrás`;
  }

  const diffHours = Math.round(diffMinutes / 60);
  if (Math.abs(diffHours) < 24) {
    const hours = Math.abs(diffHours);
    return `${hours} ${hours === 1 ? 'hora' : 'horas'} atrás`;
  }

  const diffDays = Math.round(diffHours / 24);
  if (Math.abs(diffDays) < 30) {
    const days = Math.abs(diffDays);
    return `${days} ${days === 1 ? 'dia' : 'dias'} atrás`;
  }

  const diffMonths = Math.round(diffDays / 30);
  if (Math.abs(diffMonths) < 12) {
    const months = Math.abs(diffMonths);
    return `${months} ${months === 1 ? 'mês' : 'meses'} atrás`;
  }

  const diffYears = Math.round(diffMonths / 12);
  const years = Math.abs(diffYears);
  return `${years} ${years === 1 ? 'ano' : 'anos'} atrás`;
};

/**
 * Converte uma string ISO em data local apenas, sem horário.
 */
export const formatDateOnly = (iso?: string | null): string => {
  // Garante retorno amigável em caso de ausência ou erro de parsing
  const parsedDate = parseIsoAsUtc(iso);
  if (!parsedDate) return '—';

  return parsedDate.toLocaleDateString('pt-BR');
};

export const formatDateTime = (iso?: string | null): string => {
  const parsedDate = parseIsoAsUtc(iso);
  if (!parsedDate) return '—';

  return parsedDate.toLocaleString('pt-BR');
};

export const parseUtcDate = parseIsoAsUtc;
