import axios, {
  AxiosError,
  AxiosInstance,
  AxiosRequestConfig,
  AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import { getApiUrl } from './config';
import { getStoredAccessToken } from '../auth/storage';

/**
 * Interface genérica para envelopes paginados aceitando tanto o formato legado quanto o formato alvo.
 */
export interface PaginatedPayload<T> {
  items: T[];
  total?: number;
  page?: number;
  per_page?: number;
  meta?: {
    total?: number;
    page?: number;
    per_page?: number;
  };
}

/**
 * Estrutura normalizada utilizada nas páginas do frontend.
 */
export interface NormalizedPagination<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}

/**
 * Converte envelopes paginados para a estrutura unificada, aceitando meta ou atributos no root.
 */
export const normalizePaginated = <T>(payload: PaginatedPayload<T>): NormalizedPagination<T> => {
  const metaSource = payload.meta ?? {};

  return {
    items: payload.items ?? [],
    total: payload.total ?? metaSource.total ?? 0,
    page: payload.page ?? metaSource.page ?? 1,
    per_page: payload.per_page ?? metaSource.per_page ?? payload.items?.length ?? 0,
  };
};

/**
 * Provedor de token configurável para permitir integração com o AuthContext.
 */
let tokenProvider: (() => string | null | Promise<string | null>) | null = null;

/**
 * Registra função responsável por fornecer o token em tempo de requisição.
 */
export const setAuthTokenProvider = (
  provider: () => string | null | Promise<string | null>,
): void => {
  tokenProvider = provider;
};

/**
 * Remove provider customizado, voltando a usar o storage local como fallback.
 */
export const clearAuthTokenProvider = (): void => {
  tokenProvider = null;
};

/**
 * Instância compartilhada do Axios com timeout padrão e interceptores de autenticação.
 */
export const apiClient: AxiosInstance = axios.create({
  baseURL: getApiUrl(),
  timeout: 15_000,
});

apiClient.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  const providedToken = tokenProvider ? await Promise.resolve(tokenProvider()) : null;
  const storedToken = providedToken ?? getStoredAccessToken();

  if (storedToken) {
    config.headers = config.headers ?? {};
    if (!('Authorization' in config.headers)) {
      config.headers.Authorization = `Bearer ${storedToken}`;
    }
  }

  const headers = config.headers || {};
  if (!('Accept' in headers)) {
    (headers as Record<string, unknown>).Accept = 'application/json';
  }

  config.headers = headers;

  return config;
});

/**
 * Normaliza mensagens de erro retornadas pelo backend ou pelo próprio Axios.
 */
export const extractErrorMessage = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError;
    const responseData = axiosError.response?.data as Record<string, unknown> | undefined;
    const prioritizedFields: Array<'detail' | 'message' | 'msg'> = ['detail', 'message', 'msg'];

    if (responseData) {
      for (const field of prioritizedFields) {
        const value = responseData[field];
        if (typeof value === 'string' && value.trim()) {
          return value;
        }
      }
    }

    if (typeof axiosError.response?.status === 'number') {
      return `Erro ${axiosError.response.status}`;
    }

    if (axiosError.message) {
      return axiosError.message;
    }
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return 'Erro desconhecido ao comunicar com o servidor';
};

/**
 * Auxiliar para extrair o corpo JSON em erros sem quebrar o fluxo de interceptores.
 */
export const getResponseData = <T>(response: AxiosResponse<T> | undefined): T | null => {
  if (!response) {
    return null;
  }

  return response.data ?? null;
};
