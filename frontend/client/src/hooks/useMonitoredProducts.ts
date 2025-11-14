import { useCallback, useMemo } from 'react';
import { useInfiniteQuery, useQueryClient, type InfiniteData } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { MonitoredProduct, PaginatedMonitoredProducts, getMonitoredProducts, getMonitoredProduct } from '@/lib/api';

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
  optimisticallyIncrementCompetitorsCount: (productId: string) => void;
  refreshProductById: (productId: string) => Promise<MonitoredProduct | null>;
  /** Alias semântico usado em fluxos reativos para atualizar um item específico. */
  refetchItem: (productId: string) => Promise<MonitoredProduct | null>;
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
  const queryClient = useQueryClient();
  const queryKey = ['monitored-products', token] as const;

  const query = useInfiniteQuery<PaginatedMonitoredProducts>({
    queryKey,
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

  /**
   * Atualiza o cache local incrementando o contador de concorrentes do produto.
   * Mantém imutabilidade das páginas para que a lista virtualizada reflita o novo valor.
   */
  const optimisticallyIncrementCompetitorsCount = useCallback(
    (productId: string) => {
      if (!token) {
        return;
      }

      queryClient.setQueryData<InfiniteData<PaginatedMonitoredProducts>>(queryKey, (data) => {
        if (!data) {
          return data;
        }

        const nextPages = data.pages.map((page) => ({
          ...page,
          items: page.items.map((item) => {
            if (item.id !== productId) {
              return item;
            }

            const currentCount = item.competitors_count ?? 0;

            return {
              ...item,
              competitors_count: currentCount + 1,
            };
          }),
        }));

        return {
          ...data,
          pages: nextPages,
        };
      });
    },
    [queryClient, queryKey, token],
  );

  /**
   * Recarrega os dados de um monitorado específico atualizando o cache local.
   * Evita refetch completo da lista quando apenas um item mudou.
   */
  const refreshProductById = useCallback(
    async (productId: string): Promise<MonitoredProduct | null> => {
      if (!token) {
        throw new Error('Sessão expirada. Faça login novamente para atualizar o produto monitorado.');
      }

      const freshProduct = await getMonitoredProduct(token, productId);
      let wasUpdated = false;

      queryClient.setQueryData<InfiniteData<PaginatedMonitoredProducts>>(queryKey, (data) => {
        if (!data) {
          return data;
        }

        const nextPages = data.pages.map((page) => ({
          ...page,
          items: page.items.map((item) => {
            if (item.id !== productId) {
              return item;
            }

            wasUpdated = true;
            return freshProduct;
          }),
        }));

        if (!wasUpdated) {
          return data;
        }

        return {
          ...data,
          pages: nextPages,
        };
      });

      if (!wasUpdated) {
        return null;
      }

      return freshProduct;
    },
    [queryClient, queryKey, token],
  );

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
    optimisticallyIncrementCompetitorsCount,
    refreshProductById,
    refetchItem: refreshProductById,
  };
};
