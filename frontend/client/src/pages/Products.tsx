import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Virtuoso } from 'react-virtuoso';
import { useLocation } from 'wouter';
import { Loader2, AlertCircle, RotateCcw } from 'lucide-react';
import { useMonitoredProducts } from '@/hooks/useMonitoredProducts';
import { Card, CardContent } from '@/components/ui/data-display/card';
import { Button } from '@/components/ui/button/button';
import { Skeleton } from '@/components/ui/data-display/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/feedback/alert';
import MonitoredProductCard from '@/components/MonitoredProductCard';
import { toast } from 'sonner';
import type { MonitoredProduct } from '@/lib/api';
import AddCompetitorModal from '@/components/modals/AddCompetitorModal';


/**
 * Página: Produtos Monitorados
 *
 * Lista produtos monitorados com paginação infinita virtualizada (react-virtuoso).
 * - Usa hook useMonitoredProducts para buscar dados paginados (react-query / similar).
 * - Fornece ações: adicionar produto, ver concorrentes, atualizar um produto ou recarregar a lista.
 * - Mensagens e estados de carregamento são exibidos via componentes de UI e toast.
 */

export default function Products() {
  // Hook custom que retorna dados paginados, estados e funções de controle
  const {
    products,
    total,
    perPage,
    isLoading,
    isFetching,
    isFetchingNextPage,
    hasNextPage,
    error,
    fetchNextPage,
    refetch,
    optimisticallyIncrementCompetitorsCount,
    refreshProductById
  } = useMonitoredProducts();

  // Router imperativo via wouter
  const [, navigate] = useLocation();

  // Estado local que guarda o id do produto que está sendo atualizado individualmente
  const [refreshingProductId, setRefreshingProductId] = useState<string | null>(null);
  // Produto associado ao modal de adição de concorrente.
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);

  // Produto atual derivado da lista global garantindo sincronismo com atualizações otimistas.
  const selectedProduct = useMemo(
    () => products.find((item) => item.id === selectedProductId) ?? null,
    [products, selectedProductId],
  );

  useEffect(() => {
    if (selectedProductId && !selectedProduct) {
      setSelectedProductId(null);
    }
  }, [selectedProduct, selectedProductId]);

  // Rótulo resumido da faixa exibida (ex: "Exibindo X de Y")
  const rangeLabel = useMemo(() => {
    if (total === 0) {
      return 'Nenhum produto monitorado no momento.';
    }

    return `Exibindo ${products.length} de ${total} produtos monitorados`;
  }, [products.length, total]);

  // Indica se algum produto está sendo atualizado individualmente
  const isRefreshingList = refreshingProductId !== null;

  /**
   * Atualiza um produto específico recarregando seus dados individualmente.
   * Protege contra múltiplos refreshes concorrentes.
   */
  const handleRefreshProduct = async (productId: string) => {
    if (isRefreshingList) {
      return;
    }

    setRefreshingProductId(productId);

    try {
      const refreshed = await refreshProductById(productId);
      if (!refreshed) {
        await refetch();
      }
      toast.success('Produto atualizado com sucesso.');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro ao atualizar produto';
      toast.error(message);
    } finally {
      setRefreshingProductId(null);
    }
  };

  /**
   * Tenta recarregar a lista inteira e mostra erro via toast se falhar.
   * Usado no botão de retry do alerta de erro.
   */
  const handleRetry = () => {
    refetch().catch((err) => {
      const message = err instanceof Error ? err.message : 'Erro ao recarregar produtos';
      toast.error(message);
    });
  };

  /** Abre modal card-first para adicionar concorrente ao produto escolhido. */
  const handleAddCompetitor = (productId: string) => {
    setSelectedProductId(productId);
  };

  /** Navega para a lista completa de concorrentes daquele produto. */
  const handleViewCompetitors = (productId: string) => {
    navigate(`/competitors/${productId}`);
  };

  /** Fecha modal de concorrentes limpando seleção atual. */
  const handleCloseAddCompetitor = useCallback(() => {
    setSelectedProductId(null);
  }, []);

  /** Atualiza contador de concorrentes no cache após agendamento bem-sucedido. */
  const handleCompetitorScheduled = useCallback(
    (options: { keepOpen: boolean; product: MonitoredProduct }) => {
      const productId = options.product.id;

    optimisticallyIncrementCompetitorsCount(productId);

      refreshProductById(productId)
        .then((refreshed) => {
          if (!refreshed) {
            return refetch();
          }
          return undefined;
        })
        .catch((error) => {
          const message =
            error instanceof Error
              ? error.message
              : 'Erro ao atualizar produto após adicionar concorrente.';
          toast.error(message);
        });
    },
    [optimisticallyIncrementCompetitorsCount, refreshProductById, refetch],
  );

  /**
   * Trigger para carregar a próxima página de resultados.
   * Prevê chamadas duplicadas quando já está carregando a próxima página.
   */
  const handleLoadMore = () => {
    if (!hasNextPage || isFetchingNextPage) {
      return;
    }

    fetchNextPage().catch((err) => {
      const message = err instanceof Error ? err.message : 'Erro ao carregar mais produtos';
      toast.error(message);
    });
  };

  // Tela de carregamento inicial (skeletons)
  if (isLoading) {
    return (
      <div className="space-y-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Produtos Monitorados</h1>
          <p className="text-muted-foreground mt-2">Carregando produtos monitorados...</p>
        </div>
        <div className="space-y-4">
          {[1, 2, 3].map((item) => (
            <Card key={item}>
              <CardContent className="pt-6">
                <Skeleton className="h-24 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  const isEmpty = total === 0;

  return (
    <div className="space-y-6">
      {/* Cabeçalho com título, subtítulo e botão de adicionar */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Produtos Monitorados</h1>
          <p className="text-muted-foreground mt-2">
            {isFetching && !isLoading ? 'Atualizando lista de produtos...' : rangeLabel}
          </p>
          <p className="text-xs text-muted-foreground">Página atual limitada a {perPage} itens por requisição.</p>
        </div>
        {/* Botão para navegar até a tela de adicionar produto */}
        <Button onClick={() => navigate('/add')}>Adicionar Produto</Button>
      </div>

      {/* Exibe alerta de erro quando a query falha */}
      {error && (
        <Alert variant="destructive" className="items-start">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Erro ao carregar produtos</AlertTitle>
          <AlertDescription className="space-y-3">
            <p>{error}</p>
            <Button variant="outline" size="sm" onClick={handleRetry} className="gap-2" type="button">
              <RotateCcw className="h-4 w-4" /> Tentar novamente
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Mostra estado vazio quando não há produtos */}
      {isEmpty ? (
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-muted-foreground mb-4">Nenhum produto monitorado ainda</p>
            <Button onClick={() => navigate('/add')}>Adicionar primeiro produto</Button>
          </CardContent>
        </Card>
      ) : (
        // Lista virtualizada para grande quantidade de itens (melhor performance)
        <Virtuoso
          useWindowScroll
          data={products}
          endReached={handleLoadMore}
          overscan={200}
          components={{
            // Footer personalizado que mostra estado de carregamento ou espaço vazio
            Footer: () => (
              hasNextPage ? (
                <div className="py-6 text-center text-sm text-muted-foreground">
                  {isFetchingNextPage ? (
                    <span className="inline-flex items-center justify-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" /> Carregando mais produtos...
                    </span>
                  ) : (
                    'Role para carregar mais produtos.'
                  )}
                </div>
              ) : (
                <div className="py-4" />
              )
            ),
          }}
          // Renderiza cada item usando o componente MonitoredProductCard
          itemContent={(_index: number, product: MonitoredProduct) => (
            <div key={product.id} className="pb-4">
              <MonitoredProductCard
                product={product}
                onViewCompetitors={() => handleViewCompetitors(product.id)}
                onAddCompetitor={() => handleAddCompetitor(product.id)}
                onRefresh={() => handleRefreshProduct(product.id)}
                isRefreshing={isRefreshingList}
                isRefreshingSelf={isRefreshingList && refreshingProductId === product.id}
              />
            </div>
          )}
        />
      )}

      {selectedProduct && (
        <AddCompetitorModal
          product={selectedProduct}
          isOpen={Boolean(selectedProduct)}
          onClose={handleCloseAddCompetitor}
          onScheduled={handleCompetitorScheduled}
        />
      )}
    </div>
  );
}
