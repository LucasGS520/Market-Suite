import { useMemo } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { MonitoredProduct, PaginatedMonitoredProducts, getMonitoredProducts } from '@/lib/api';

/** 
 * Número padrão de itens buscados por página ao paginar produtos monitorados. 
 */
export const MONITORED_PRODUCTS_PER_PAGE = 50;

/** 
 * Estrutura de retorno padronizada pelo hook para facilitar o consumo na UI. 
 */
type UseMonitoredProductsResult = {
  products: MonitoredProduct[];
  total: number;
  perPage: number;
  isLoading: boolean;
  isFetching: boolean;
  isFetchingNextPage: boolean;
  hasNextPage: boolean;
  error: string | null;
  fetchNextPage: () => Promise<unknown>;
  refetch: () => Promise<void>;
};

/**
 * Hook para gerenciar lista de produtos monitorados com páginação infinita.
 *
 * - Utiliza React Query para armazenar em cache e invalidar resultados.
 * - Concatena páginas já carregadas expondo a lista total para a UI.
 * - Oferece estados de carregamento globais e auxiliares para carregamento incremental.
 */
export const useMonitoredProducts = (): UseMonitoredProductsResult => {
  const { token } = useAuth();

  const query = useInfiniteQuery<PaginatedMonitoredProducts>({
    queryKey: ['monitored-products', token] as const,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 1,
    queryFn: async ({ pageParam = 1 }): Promise<PaginatedMonitoredProducts> => {
      const currentPage = typeof pageParam === 'number' && Number.isFinite(pageParam) ? pageParam : 1;
      if (!token) {
        return {
          items: [],
          total: 0,
          page: currentPage,
          per_page: MONITORED_PRODUCTS_PER_PAGE,
        };
      }
      return getMonitoredProducts(token, {
        page: currentPage,
        per_page: MONITORED_PRODUCTS_PER_PAGE,
      });
    },
    getNextPageParam: (lastPage) => {
      const totalPages = lastPage.per_page > 0 ? Math.ceil(lastPage.total / lastPage.per_page) : 0;
      if (totalPages === 0) {
        return undefined;
      }
      return lastPage.page < totalPages ? lastPage.page + 1 : undefined;
    },
  });

  const aggregatedPages = query.data?.pages ?? ([] as PaginatedMonitoredProducts[]);
  const products = useMemo(
    () => aggregatedPages.flatMap((page: PaginatedMonitoredProducts) => page.items),
    [aggregatedPages],
  );

  const total = aggregatedPages[0]?.total ?? 0;
  const perPage = aggregatedPages[0]?.per_page ?? MONITORED_PRODUCTS_PER_PAGE;
  const errorMessage = query.error instanceof Error ? query.error.message : null;

  const refetch = async () => {
    const result = await query.refetch();
    if (result.error) {
      throw result.error;
    }
    return;
  };

  return {
    products,
    total,
    perPage,
    isLoading: query.status === 'loading',
    isFetching: query.isFetching,
    isFetchingNextPage: query.isFetchingNextPage,
    hasNextPage: Boolean(query.hasNextPage),
    error: errorMessage,
    fetchNextPage: () => query.fetchNextPage(),
    refetch,
  };
};
