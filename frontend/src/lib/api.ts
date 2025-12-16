import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';

/**
 * Cliente HTTP centralizado para a aplicação frontend.
 * - Configura baseURL a partir da variável de ambiente VITE_API_URL (com fallback).
 * - Adiciona interceptor de request para injetar o token de acesso (Authorization: Bearer ...).
 * - Adiciona interceptor de response para tratar 401 (tentar renovar token via /auth/refresh).
 */

const API_BASE_URL =
  import.meta.env.VITE_API_URL ??
  (typeof location !== 'undefined' ? `${location.protocol}//${location.hostname}:8000` : 'http://localhost:8000');

// Ajuste resiliente: se a base configurada apontar para localhost, mas o usuário
// está acessando o frontend por outro host (ex: 192.168.15.150), substituir
// automaticamente o hostname para evitar que o browser tente se conectar ao
// `localhost` da máquina remota.
let RESOLVED_API_BASE = API_BASE_URL;
if (typeof location !== 'undefined') {
  try {
    const parsed = new URL(API_BASE_URL);
    const isLocalHost = parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1';
    const clientHostIsRemote = location.hostname && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1';
    if (isLocalHost && clientHostIsRemote) {
      parsed.hostname = location.hostname;
      RESOLVED_API_BASE = parsed.toString().replace(/\/$/, '');
    }
  } catch {
    // se não for uma URL válida, manter o valor original
  }
}

// Cliente HTTP Axios configurado com baseURL e cabeçalho padrão
export const apiClient = axios.create({
  baseURL: RESOLVED_API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Em dev, logar a baseURL utilizada para facilitar diagnóstico remoto
if (import.meta.env.DEV) {
  // eslint-disable-next-line no-console
  console.debug('[api] API_BASE_URL =', API_BASE_URL, '=> RESOLVED_API_BASE =', RESOLVED_API_BASE);
}

/**
 * Função utilitária para limpar tokens e redirecionar o usuário para a tela de login.
 * Mantém comportamento reutilizável em casos de falha de autenticação.
 */
const redirectToLogin = (): void => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  // Redireciona para rota de login da aplicação
  window.location.href = '/login';
};

// Interceptor de request:
// - Injeta o token de acesso (se existir) no header Authorization de todas as requisições.
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('access_token');
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
  refresh_token: string;
}

/**
 * Interceptor de response:
 * - Passa a resposta quando bem-sucedida.
 * - Ao receber 401 (não autorizado), tenta renovar o access_token usando o refresh_token.
 *   - Se não houver refresh_token, limpa estado e redireciona para login.
 *   - Se a renovação for bem-sucedida, atualiza tokens em localStorage e re-executa a requisição original.
 *   - Em caso de falha ao renovar, limpa estado e redireciona para login.
 */
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    // Se receber 401 (Unauthorized) e não for tentativa de retry, tentar renovar token
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const refreshToken = localStorage.getItem('refresh_token');

        if (!refreshToken) {
          // Sem refresh token disponível: limpar e redirecionar para login
          redirectToLogin();
          return Promise.reject(error);
        }

        // Tentar renovar o token no endpoint de refresh
        const response = await axios.post<RefreshResponse>(`${RESOLVED_API_BASE}/auth/refresh`, {
          refresh_token: refreshToken,
        });

        const { access_token, refresh_token: newRefreshToken } = response.data;

        // Armazenar novos tokens no localStorage
        localStorage.setItem('access_token', access_token);
        localStorage.setItem('refresh_token', newRefreshToken);

        // Atualizar header Authorization da requisição original e refazer a chamada
        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${access_token}`;
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
