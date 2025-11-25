/**
 * Configurações compartilhadas para montar URLs do backend e manter consistência de chamadas HTTP.
 */
const DEFAULT_API_URL = 'http://localhost:8000/';

/**
 * Normaliza a URL base recebida via variável de ambiente, aplicando fallback quando ausente ou inválida.
 */
export const normalizeBaseApiUrl = (rawUrl?: string): string => {
  const trimmed = rawUrl?.trim();

  if (!trimmed) {
    return DEFAULT_API_URL;
  }

  try {
    const parsed = new URL(trimmed);
    parsed.search = '';
    parsed.hash = '';

    const normalizedPath = parsed.pathname.replace(/\/+$/, '');
    parsed.pathname = normalizedPath ? `${normalizedPath}/` : '/';

    return parsed.toString();
  } catch (error) {
    console.warn('URL base da API inválida, retornando fallback padrão.', error);
    return DEFAULT_API_URL;
  }
};

/**
 * Retorna a URL base normalizada a partir das variáveis do Vite ou o fallback local.
 */
export const getApiUrl = () => normalizeBaseApiUrl(import.meta.env.VITE_FRONTEND_FORGE_API_URL);

/**
 * Constrói a URL final para um endpoint, garantindo ausência de barras duplicadas e preservando querystring.
 */
export const buildApiUrl = (endpoint: string): string => {
  const sanitizedEndpoint = endpoint.startsWith('/') ? endpoint.slice(1) : endpoint;
  const base = getApiUrl();

  try {
    return new URL(sanitizedEndpoint, base).toString();
  } catch (error) {
    const normalizedBase = base.endsWith('/') ? base : `${base}/`;
    return `${normalizedBase}${sanitizedEndpoint}`;
  }
};

/**
 * Monta URL de WebSocket de notificações autenticada com o token JWT atual.
 */
export const buildNotificationsWebSocketUrl = (token: string): string => {
  const base = getApiUrl();
  const url = new URL(base);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';

  const normalizedPath = url.pathname.replace(/\/+$/, '');
  url.pathname = `${normalizedPath}/ws`;
  url.search = '';
  url.hash = '';
  url.searchParams.set('token', token);

  return url.toString();
};
