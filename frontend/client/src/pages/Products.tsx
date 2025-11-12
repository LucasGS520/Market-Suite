import React, { useEffect, useMemo, useState } from 'react';
import { useMonitoredProducts } from '@/hooks/useMonitoredProducts';
import { useLocation } from 'wouter';
import { Card, CardContent } from '@/components/ui/data-display/card';
import { Button } from '@/components/ui/button/button';
import { Skeleton } from '@/components/ui/data-display/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/feedback/alert';
import { AlertCircle, RotateCcw } from 'lucide-react';
import { Pagination, PaginationContent, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from '@/components/ui/navigation/pagination';
import { toast } from 'sonner';
import MonitoredProductCard from '@/components/MonitoredProductCard';

/** Número máximo de itens por página quando ativada a paginação local. */
const ITEMS_PER_PAGE = 50;

/**
 * Componente de listagem dos produtos monitorados do usuário.
 *
 * - Consome o hook `useMonitoredProducts` para obter dados da API.
 * - Exibe estados claros de carregamento, erro e vazio.
 * - Provê ações rápidas em cada cartão (ver detalhes, atualizar, navegar para concorrentes).
 */
export default function Products() {
  const { products, isLoading, isRefreshing, error, refetch } = useMonitoredProducts();
  const [, navigate] = useLocation();

  const [refreshingProductId, setRefreshingProductId] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);

  const totalPages = useMemo(() => {
    if (products.length <= 200) {
      return 1;
    }
    return Math.max(1, Math.ceil(products.length / ITEMS_PER_PAGE));
  }, [products.length]);

  const shouldPaginate = totalPages > 1;

  useEffect(() => {
    if (!shouldPaginate && currentPage !== 1) {
      setCurrentPage(1);
      return;
    }
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, shouldPaginate, totalPages]);

  const displayedProducts = useMemo(() => {
    if (!shouldPaginate) {
      return products;
    }

    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    return products.slice(startIndex, startIndex + ITEMS_PER_PAGE);
  }, [currentPage, products, shouldPaginate]);

  const rangeLabel = useMemo(() => {
    if (!shouldPaginate) {
      return `${products.length} produtos em monitoramento`;
    }

    const start = (currentPage - 1) * ITEMS_PER_PAGE + 1;
    const end = start + displayedProducts.length - 1;
    return `Exibindo ${start}-${end} de ${products.length} produtos`;
  }, [currentPage, displayedProducts.length, products.length, shouldPaginate]);

  /**
   * Reexecuta a consulta de produtos sob demanda.
   */
  const handleRefreshProduct = async (productId: string) => {
    if (isRefreshing || refreshingProductId) {
      return;
    }

    setRefreshingProductId(productId);

    try {
      await refetch();
      toast.success('Lista de produtos atualizada.');
    } finally {
      setRefreshingProductId(null);
    }
  };

  /**
   * Permite tentar novamente a carga inicial quando ocorrer erro.
   */
  const handleRetry = () => {
    refetch().catch((err) => {
      const message = err instanceof Error ? err.message : 'Erro ao recarregar produtos';
      toast.error(message);
    });
  };

  /** Navega para a rota de cadastro de concorrente já posicionando o hash do formulário. */
  const handleAddCompetitor = (productId: string) => {
    navigate(`/competitors/${productId}#novo-concorrente`);
  };

  /** Navega para a lista completa de concorrentes. */
  const handleViewCompetitors = (productId: string) => {
    navigate(`/competitors/${productId}`);
  };

  /** Atualiza a página da paginação local. */
  const handleSelectPage = (page: number) => {
    setCurrentPage(page);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Estado de carregamento: mostra skeletons representando cards em loading
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

  // Render final quando dados já foram carregados
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Produtos Monitorados</h1>
          {/* Exibe quantidade de produtos monitorados */}
          <p className="text-muted-foreground mt-2">{rangeLabel}</p>
        </div>
        {/* Botão para navegar até a tela de adicionar produto */}
        <Button onClick={() => navigate('/add')}>Adicionar Produto</Button>
      </div>

      {error && (
        // Alertamos falha de carregamento antes de avaliar estados vazios para orientar ações imediatas
        <Alert variant="destructive" className="items-start">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Erro ao carregar produtos</AlertTitle>
          <AlertDescription className="space-y-3">
            <p>{error}</p>
            <Button
              variant="outline"
              size="sm"
              onClick={handleRetry}
              className="gap-2"
              type="button"
            >
              <RotateCcw className="h-4 w-4" />
              Tentar novamente
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {products.length === 0 ? (
        // Estado vazio: orienta o usuário a adicionar o primeiro produto
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-muted-foreground mb-4">Nenhum produto monitorado ainda</p>
            <Button onClick={() => navigate('/add')}>Adicionar primeiro produto</Button>
          </CardContent>
        </Card>
      ) : (
        // Lista de produtos: cada item é um Card com informações e ações
        <div className="space-y-4">
          {displayedProducts.map((product) => (
            <MonitoredProductCard
              key={product.id}
              product={product}
              onViewCompetitors={() => handleViewCompetitors(product.id)}
              onAddCompetitor={() => handleAddCompetitor(product.id)}
              onRefresh={() => handleRefreshProduct(product.id)}
              isRefreshing={isRefreshing || Boolean(refreshingProductId)}
              isRefreshingSelf={isRefreshing && refreshingProductId === product.id}
            />
          ))}
        </div>
      )}

      {shouldPaginate && products.length > 0 && (
        <Pagination className="pt-4">
          <PaginationContent>
            <PaginationItem>
              <PaginationPrevious
                href="#"
                onClick={(event) => {
                  event.preventDefault();
                  if (currentPage > 1) {
                    handleSelectPage(currentPage - 1);
                  }
                }}
                aria-disabled={currentPage === 1}
                tabIndex={currentPage === 1 ? -1 : undefined}
                className={currentPage === 1 ? 'pointer-events-none opacity-50' : undefined}
              />
            </PaginationItem>
            {Array.from({ length: totalPages }, (_, index) => index + 1).map((pageNumber) => (
              <PaginationItem key={pageNumber}>
                <PaginationLink
                  href="#"
                  isActive={pageNumber === currentPage}
                  onClick={(event) => {
                    event.preventDefault();
                    handleSelectPage(pageNumber);
                  }}
                  size="default"
                >
                  {pageNumber}
                </PaginationLink>
              </PaginationItem>
            ))}
            <PaginationItem>
              <PaginationNext
                href="#"
                onClick={(event) => {
                  event.preventDefault();
                  if (currentPage < totalPages) {
                    handleSelectPage(currentPage + 1);
                  }
                }}
                aria-disabled={currentPage === totalPages}
                tabIndex={currentPage === totalPages ? -1 : undefined}
                className={currentPage === totalPages ? 'pointer-events-none opacity-50' : undefined}
              />
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      )}
    </div>
  );
}
