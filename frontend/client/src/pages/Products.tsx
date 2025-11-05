import React from 'react';
import { useMonitoredProducts } from '@/hooks/useMonitoredProducts';
import { useLocation } from 'wouter';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/data-display/card';
import { Button } from '@/components/ui/button/button';
import { Badge } from '@/components/ui/data-display/badge';
import { AlertCircle, TrendingUp, ExternalLink } from 'lucide-react';
import { Skeleton } from '@/components/ui/data-display/skeleton';

/**
 * Products.tsx
 * Componente de listagem de produtos monitorados.
 * - Busca produtos via hook personalizado `useMonitoredProducts`
 * - Mostra skeletons enquanto carrega
 * - Permite navegar para adicionar produto ou ver concorrentes
 */

/** Componente principal que renderiza a lista de produtos monitorados */
export default function Products() {
  // Hook que retorna os produtos e estado de carregamento
  const { products, isLoading } = useMonitoredProducts();

  // Hook do wouter para navegação (navigate)
  const [, navigate] = useLocation();

  // Estado de carregamento: mostra skeletons representando cards em loading
  if (isLoading) {
    return (
      <div className="space-y-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Produtos Monitorados</h1>
        </div>
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            // Skeletons como placeholder visual durante fetch dos dados
            <Card key={i}>
              <CardContent className="pt-6">
                <Skeleton className="h-20 w-full" />
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Produtos Monitorados</h1>
          {/* Exibe quantidade de produtos monitorados */}
          <p className="text-muted-foreground mt-2">{products.length} produtos em monitoramento</p>
        </div>
        {/* Botão para navegar até a tela de adicionar produto */}
        <Button onClick={() => navigate('/add')}>Adicionar Produto</Button>
      </div>

      {products.length === 0 ? (
        // Estado vazio: orienta o usuário a adicionar o primeiro produto
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-muted-foreground mb-4">Nenhum produto monitorado ainda</p>
            <Button onClick={() => navigate('/add')}>Adicionar Primeiro Produto</Button>
          </CardContent>
        </Card>
      ) : (
        // Lista de produtos: cada item é um Card com informações e ações
        <div className="space-y-4">
          {products.map((product) => (
            // Marca visual quando o produto está em alerta (bordas vermelhas)
            <Card key={product.id} className={product.status === 'alert' ? 'border-red-200 dark:border-red-800' : ''}>
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    {/* Identificação do produto */}
                    <CardTitle className="text-lg">{product.name_identification}</CardTitle>
                    {/* Data da última atualização formatada para pt-BR */}
                    <p className="text-sm text-muted-foreground mt-1">
                      Última atualização: {new Date(product.last_update).toLocaleDateString('pt-BR')}
                    </p>
                  </div>

                  {/* Badge que indica status do produto (Alerta / OK) */}
                  <Badge variant={product.status === 'alert' ? 'destructive' : 'default'}>
                    {product.status === 'alert' ? 'Alerta' : 'OK'}
                  </Badge>
                </div>
              </CardHeader>

              <CardContent className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  {/* Exibe preço atual do usuário */}
                  <div>
                    <p className="text-xs text-muted-foreground">Seu Preço</p>
                    <p className="text-xl font-bold">R$ {product.current_price.toFixed(2)}</p>
                  </div>

                  {/* Exibe preço alvo configurado para monitoramento */}
                  <div>
                    <p className="text-xs text-muted-foreground">Preço Alvo</p>
                    <p className="text-xl font-bold">R$ {product.target_price.toFixed(2)}</p>
                  </div>

                  {/* Número de concorrentes monitorados para este produto */}
                  <div>
                    <p className="text-xs text-muted-foreground">Concorrentes</p>
                    <p className="text-xl font-bold">{product.competitors_count}</p>
                  </div>
                </div>

                <div className="flex gap-2 pt-2">
                  {/* Abre o anúncio original em uma nova aba */}
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1"
                    onClick={() => window.open(product.product_url, '_blank')}
                  >
                    <ExternalLink className="mr-2 h-4 w-4" />
                    Ver Anúncio
                  </Button>

                  {/* Navega para a lista de concorrentes do produto */}
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1"
                    onClick={() => navigate(`/competitors/${product.id}`)}
                  >
                    <TrendingUp className="mr-2 h-4 w-4" />
                    Ver Concorrentes
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
