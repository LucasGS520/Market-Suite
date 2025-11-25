/**
 * Utilidades de armazenamento e eventos relacionados a tokens JWT do usuário.
 */
export const ACCESS_TOKEN_STORAGE_KEY = 'auth_token';
export const REFRESH_TOKEN_STORAGE_KEY = 'auth_refresh_token';
export const TOKENS_REFRESHED_EVENT = 'auth-tokens-refreshed';
export const SESSION_EXPIRED_EVENT = 'session-expired';

/** Lê o access token persistido (quando disponível no ambiente de navegador). */
export const getStoredAccessToken = (): string | null => {
  if (typeof window === 'undefined') {
    return null;
  }

  return localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
};

/** Lê o refresh token persistido (quando disponível no ambiente de navegador). */
export const getStoredRefreshToken = (): string | null => {
  if (typeof window === 'undefined') {
    return null;
  }

  return localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
};

/** Persiste o par de tokens no localStorage garantindo limpeza segura quando faltante. */
export const persistTokens = (accessToken: string, refreshToken?: string | null): void => {
  if (typeof window === 'undefined') {
    return;
  }

  localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, accessToken);

  if (refreshToken) {
    localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, refreshToken);
  } else {
    localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
  }
};

/** Remove tokens persistidos liberando cache local para novas sessões. */
export const clearStoredTokens = (): void => {
  if (typeof window === 'undefined') {
    return;
  }

  localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
  localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
};
