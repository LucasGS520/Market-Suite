import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import {
  clearAccessToken,
  getAccessToken,
  setAccessToken,
} from '../utils/authTokens';

/**
 * Cliente HTTP centralizado para a aplicação frontend.
 * - Configura baseURL a partir de VITE_API_URL (obrigatório em staging/prod).
 * - Adiciona interceptor de request para injetar o token de acesso (Authorization: Bearer ...).
 * - Adiciona interceptor de response para tratar 401 (tentar renovar token via /auth/refresh).
 */

const API_BASE_URL: string = import.meta.env.VITE_API_URL;

if (!API_BASE_URL) {
  throw new Error(
    '[api] VITE_API_URL não definido. ' +
    'Configure a variável no arquivo .env adequado antes de executar o build.'
  );
}

// Cliente HTTP Axios configurado com baseURL e cabeçalho padrão
export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  // Mantém cookies HttpOnly ativos para refresh via backend
  withCredentials: true,
});

// Em dev, logar a baseURL utilizada para facilitar diagnóstico
if (import.meta.env.DEV) {
  console.debug('[api] VITE_API_URL =', API_BASE_URL);
}

/**
 * Função utilitária para limpar tokens e redirecionar o usuário para a tela de login.
 * Mantém comportamento reutilizável em casos de falha de autenticação.
 */
const redirectToLogin = (): void => {
  clearAccessToken();
  // Redireciona para rota de login da aplicação
  window.location.href = '/login';
};

// Interceptor de request:
// - Injeta o token de acesso (se existir) no header Authorization de todas as requisições.
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getAccessToken();
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Tipagem esperada da resposta do endpoint de refresh
interface RefreshResponse {
  access_token: string;
}

let refreshPromise: Promise<string> | null = null;

/**
 * Renova o access token utilizando refresh token em cookie ou no payload
 */
const refreshAccessToken = async (): Promise<string> => {
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    // A rota/auth/refresh aceita apenas POST e lê o cookie HttpOnly
    const response = await apiClient.post<RefreshResponse>('/auth/refresh');
    const { access_token } = response.data;
    setAccessToken(access_token);
    return access_token;
  })();

  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
};

/**
 * Interceptor de response:
 * - Passa a resposta quando bem-sucedida.
 * - Ao receber 401 (não autorizado), tenta renovar o access_token usando o refresh_token.
 *   - Se não houver refresh_token, limpa estado e redireciona para login.
 *   - Se a renovação for bem-sucedida, atualiza tokens em memória/cookie e re-executa a requisição original.
 *   - Em caso de falha ao renovar, limpa estado e redireciona para login.
 */
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    const endpoint = originalRequest.url ?? '';
    const isAuthEndpoint = endpoint.includes('/auth/login') || endpoint.includes('/auth/refresh') || endpoint.includes('/auth/logout');

    // Se receber 401 (Unauthorized) e não for tentativa de retry, tentar renovar token
    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
      originalRequest._retry = true;

      try {
        const accessToken = await refreshAccessToken();

        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${accessToken}`;
        }
        return apiClient(originalRequest);
      } catch (refreshError) {
        // Falha ao renovar token: limpar estado e redirecionar para login
        redirectToLogin();
        return Promise.reject(refreshError);
      }
    }

    // Para outros erros, propagar normalmente
    return Promise.reject(error);
  }
);

export default apiClient;
