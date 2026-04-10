import type { AxiosError } from 'axios';
import type { ApiErrorResponse } from '../types';

/**
 * Extrai uma mensagem de erro legível da resposta da API.
 *
 * O backend pode retornar `detail` de duas formas:
 * - string  → erro simples (ex: "Produto não encontrado")
 * - array   → erro de validação Pydantic (ex: URL inválida, campo faltando)
 *
 * React não consegue renderizar objetos/arrays diretamente — esta função
 * normaliza os dois casos para sempre retornar uma string legível.
 */
export function getApiErrorDetail(
  error: unknown,
  fallback = 'Erro desconhecido',
): string {
  const axiosError = error as AxiosError<ApiErrorResponse>;
  const detail = axiosError?.response?.data?.detail;

  if (!detail) return fallback;

  // Erro de validação Pydantic: detail é um array de objetos
  if (Array.isArray(detail)) {
    const first = detail[0];
    return first?.msg ?? fallback;
  }

  // Erro simples: detail é string
  if (typeof detail === 'string') return detail;

  return fallback;
}
