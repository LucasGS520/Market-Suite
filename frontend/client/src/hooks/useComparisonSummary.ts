/**
 * Hook responsável por orquestrar o carregamento lazy do resumo competitivo.
 */
import { useEffect, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { ComparisonSummary, getComparisonSummary } from '@/lib/api';

/**
 * Parâmetros aceitos pelo hook de resumo competitivo.
 */
type UseComparisonSummaryOptions = {
  /** Resumo pré-carregado entregue pela listagem quando disponível. */
  initialSummary?: ComparisonSummary | null;
};

/**
 * Estrutura retornada pelo hook de resumo competitivo.
 * 
 * - summary: dados normalizados do resumo competitivo (pode ser `null` quando backend ainda não calculou).
 * - isLoading: indica carregamento ativo (tanto primeira carga quanto recarregamentos).
 * - error: representa erro da última tentativa de carregamento, caso exista.
 * - hasAttemptedFetch: informa se já tentamos buscar o recurso ao menos uma vez.
 * - loadSummary: dispara a busca do resumo competitivo sob demanda.
 * - refetchSummary: força nova tentativa de carregamento mesmo após sucesso prévio.
 * 
 */
type UseComparisonSummaryResult = {
  summary: ComparisonSummary | null | undefined;
  isLoading: boolean;
  error: Error | null;
  hasAttemptedFetch: boolean;
  loadSummary: () => Promise<ComparisonSummary | null | undefined>;
  refetchSummary: () => Promise<ComparisonSummary | null | undefined>;
};

/**
 * Hook responsável por abstrair o carregamento lazy do resumo competitivo.
 *
 * - Usa React Query para cachear resultados por produto monitorado.
 * - Aceita um resumo inicial fornecido pela listagem (`initialSummary`).
 * - Apenas dispara requisições quando solicitado via `loadSummary`/`refetchSummary`.
 */
export const useComparisonSummary = (
  monitoredId: string,
  options: UseComparisonSummaryOptions = {},
): UseComparisonSummaryResult => {
  const { token } = useAuth();
  const queryClient = useQueryClient();

  const initialSummary = options.initialSummary;
  const queryKey = useMemo(() => ['comparison-summary', monitoredId, token] as const, [monitoredId, token]);

  const query = useQuery<ComparisonSummary | null>({
    queryKey,
    enabled: false,
    initialData: initialSummary === undefined ? undefined : initialSummary,
    staleTime: 60_000,
    queryFn: async () => {
      if (!token) {
        throw new Error('Sessão expirada. Faça login novamente para visualizar os concorrentes.');
      }

      return getComparisonSummary(token, monitoredId);
    },
  });

  useEffect(() => {
    // Sincroniza atualizações vindas do endpoint de listagem com o cache do React Query.
    if (initialSummary !== undefined) {
      queryClient.setQueryData(queryKey, initialSummary);
    }
  }, [initialSummary, queryClient, queryKey]);

  const loadSummary = async () => {
    const result = await query.refetch();

    if (result.error) {
      throw result.error;
    }

    return result.data;
  };

  return {
    summary: query.data,
    isLoading: query.isFetching,
    error: query.error instanceof Error ? query.error : null,
    hasAttemptedFetch: query.isFetched || query.isFetching,
    loadSummary,
    refetchSummary: loadSummary,
  };
};

export default useComparisonSummary;
