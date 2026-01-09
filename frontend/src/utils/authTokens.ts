/**
 * Utilitários para gerenciar tokens de autenticação no frontend.
 * 
 * - access_token fica apenas em memória
 * - refresh_token (fallback) pode ser armazenado em cookies SameSite=Strict
 */

const ACCESS_TOKEN_MEMORY: { value: string | null } = { value: null };

const REFRESH_COOKIE_NAME = 'refresh_token';
const SHOULD_STORE_REFRESH_COOKIE = import.meta.env.VITE_AUTH_REFRESH_STORAGE === 'cookie';
const REFRESH_COOKIE_MAX_AGE_DAYS = 7;

/**
 * Retorna o access token em memória
 */
export const getAccessToken = (): string | null => ACCESS_TOKEN_MEMORY.value;

/**
 * Atualiza o access token em memória
 */
export const setAccessToken = (token: string | null): void => {
    ACCESS_TOKEN_MEMORY.value = token;
};

/**
 * Limpa o access token em memória
 */
export const clearAccessToken = (): void => {
    ACCESS_TOKEN_MEMORY.value = null;
};

/**
 * Retorna o refresh token armazenado em cookie (quando configurado)
 */
export const getRefreshTokenFromCookie = (): string | null => {
    if (!SHOULD_STORE_REFRESH_COOKIE || typeof document === 'undefined') {
      return null;
    }
    const cookies = document.cookie.split(';').map((cookie) => cookie.trim());
    const refreshCookie = cookies.find((cookie) => cookie.startsWith(`${REFRESH_COOKIE_NAME}=`));
    return refreshCookie ? decodeURIComponent(refreshCookie.split('=')[1] ?? '') : null;
};

/**
 * Salva o refresh token em cookie SameSite=Strict (fallback)
 */
export const setRefreshTokenCookie = (token: string): void => {
    if (!SHOULD_STORE_REFRESH_COOKIE || typeof document === 'undefined') {
        return;
    }
    const maxAgeSeconds = REFRESH_COOKIE_MAX_AGE_DAYS * 24 * 60 * 60;
    const secureFlag = typeof window !== 'undefined' && window.location.protocol === 'https:' ? '; Secure' : '';
    document.cookie = `${REFRESH_COOKIE_NAME}=${encodeURIComponent(token)}; Max-Age=${maxAgeSeconds}; Path=/; SameSite=Strict${secureFlag}`;
};

/**
 * Remove o refresh token armazenado em cookie
 */
export const clearRefreshTokenCookie = (): void => {
    if (!SHOULD_STORE_REFRESH_COOKIE || typeof document === 'undefined') {
        return;
    }
    document.cookie = `${REFRESH_COOKIE_NAME}=; Max-Age=0; Path=/; SameSite=Strict`;
};

export const shouldStoreRefreshCookie = (): boolean => SHOULD_STORE_REFRESH_COOKIE;
