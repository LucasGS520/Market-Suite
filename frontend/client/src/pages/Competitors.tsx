import React, { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useLocation } from 'wouter';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, TrendingDown, TrendingUp, ExternalLink } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import { getCompetitors, Competitor } from '@/lib/api';

export default function Competitors() {
  const { token } = useAuth();
  const [location, navigate] = useLocation();
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Extraindo o ID do produto da URL
  const productId = location.split('/').pop() || '';

  useEffect(() => {
    if (!token || !productId) return;

    const fetchCompetitors = async () => {
      try {
        const data = await getCompetitors(token, productId);
        setCompetitors(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Erro ao buscar concorrentes');
      } finally {
        setIsLoading(false);
      }
    };

    fetchCompetitors();
  }, [token, productId]);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={() => navigate('/products')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h1 className="text-3xl font-bold tracking-tight">Concorrentes</h1>
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
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" onClick={() => navigate('/products')}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Concorrentes</h1>
          <p className="text-muted-foreground mt-2">{competitors.length} concorrentes encontrados</p>
        </div>
      </div>

      {error && (
        <Card className="border-red-200 dark:border-red-800">
          <CardContent className="pt-6">
            <p className="text-red-600 dark:text-red-400">{error}</p>
          </CardContent>
        </Card>
      )}

      {competitors.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-muted-foreground mb-4">Nenhum concorrente cadastrado ainda</p>
            <Button onClick={() => navigate('/products')}>Voltar aos Produtos</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {competitors.map((competitor) => {
            const priceChange = competitor.current_price > 0 ? 'stable' : 'unknown';

            return (
              <Card key={competitor.id}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <CardTitle className="text-lg">{competitor.name}</CardTitle>
                      <p className="text-sm text-muted-foreground mt-1">
                        Última atualização: {new Date(competitor.last_update).toLocaleDateString('pt-BR')}
                      </p>
                    </div>
                    <Badge variant="outline">Concorrente</Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-muted-foreground">Preço</p>
                      <p className="text-2xl font-bold">R$ {competitor.current_price.toFixed(2)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Status</p>
                      <div className="flex items-center gap-2 mt-1">
                        {priceChange === 'stable' ? (
                          <TrendingDown className="h-4 w-4 text-green-600" />
                        ) : (
                          <TrendingUp className="h-4 w-4 text-red-600" />
                        )}
                        <span className="text-sm font-medium">Estável</span>
                      </div>
                    </div>
                  </div>

                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={() => window.open(competitor.product_url, '_blank')}
                  >
                    <ExternalLink className="mr-2 h-4 w-4" />
                    Ver Anúncio do Concorrente
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
