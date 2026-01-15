/**
 * Utilitários para gerenciar tokens de autenticação no frontend.
 *
 * - access_token fica apenas em memória
 * - refresh_token permanece apenas no cookie HttpOnly emitido pelo backend
 */

const ACCESS_TOKEN_MEMORY: { value: string | null } = { value: null };

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
