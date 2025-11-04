import React from 'react';
import { useMonitoredProducts } from '@/hooks/useMonitoredProducts';
import { useLocation } from 'wouter';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { AlertCircle, TrendingUp, ExternalLink } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';

export default function Products() {
  const { products, isLoading } = useMonitoredProducts();
  const [, navigate] = useLocation();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Produtos Monitorados</h1>
        </div>
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Produtos Monitorados</h1>
          <p className="text-muted-foreground mt-2">{products.length} produtos em monitoramento</p>
        </div>
        <Button onClick={() => navigate('/add')}>Adicionar Produto</Button>
      </div>

      {products.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-muted-foreground mb-4">Nenhum produto monitorado ainda</p>
            <Button onClick={() => navigate('/add')}>Adicionar Primeiro Produto</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {products.map((product) => (
            <Card key={product.id} className={product.status === 'alert' ? 'border-red-200 dark:border-red-800' : ''}>
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <CardTitle className="text-lg">{product.name_identification}</CardTitle>
                    <p className="text-sm text-muted-foreground mt-1">
                      Última atualização: {new Date(product.last_update).toLocaleDateString('pt-BR')}
                    </p>
                  </div>
                  <Badge variant={product.status === 'alert' ? 'destructive' : 'default'}>
                    {product.status === 'alert' ? 'Alerta' : 'OK'}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <p className="text-xs text-muted-foreground">Seu Preço</p>
                    <p className="text-xl font-bold">R$ {product.current_price.toFixed(2)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Preço Alvo</p>
                    <p className="text-xl font-bold">R$ {product.target_price.toFixed(2)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Concorrentes</p>
                    <p className="text-xl font-bold">{product.competitors_count}</p>
                  </div>
                </div>

                <div className="flex gap-2 pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1"
                    onClick={() => window.open(product.product_url, '_blank')}
                  >
                    <ExternalLink className="mr-2 h-4 w-4" />
                    Ver Anúncio
                  </Button>
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
