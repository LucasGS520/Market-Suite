// Componente de página que lista concorrentes de um produto monitorado.
// Contém carregamento, tratamento de erro e ações para abrir o anúncio do concorrente.

import React, { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useLocation } from 'wouter';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/data-display/card';
import { Button } from '@/components/ui/button/button';
import { Badge } from '@/components/ui/data-display/badge';
import { ArrowLeft, TrendingDown, TrendingUp, ExternalLink } from 'lucide-react';
import { Skeleton } from '@/components/ui/data-display/skeleton';
import { getCompetitors, Competitor } from '@/lib/api';

export default function Competitors() {
  // Recupera token do contexto de autenticação
  const { token } = useAuth();

  // Hook do roteamento (wouter): location atual e função de navegação
  const [location, navigate] = useLocation();

  // Estado local: lista de concorrentes
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  // Estado de carregamento para mostrar skeletons enquanto busca dados
  const [isLoading, setIsLoading] = useState(true);
  // Mensagem de erro simples para exibição em UI
  const [error, setError] = useState<string | null>(null);

  // Extraindo o ID do produto da URL (assume que o ID vem como última parte da rota)
  const productId = location.split('/').pop() || '';

  useEffect(() => {
    // Só tenta buscar se tivermos token e productId válidos
    if (!token || !productId) return;

    const fetchCompetitors = async () => {
      try {
        // Chamada ao client API que retorna a lista de concorrentes
        const data = await getCompetitors(token, productId);
        setCompetitors(data);
      } catch (err) {
        // Normaliza mensagem de erro para string exibível
        setError(err instanceof Error ? err.message : 'Erro ao buscar concorrentes');
      } finally {
        // Finaliza estado de loading independente do resultado
        setIsLoading(false);
      }
    };

    fetchCompetitors();
    // Reexecuta quando token ou productId mudarem
  }, [token, productId]);

  // UI de carregamento com skeletons
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

  // UI principal da página
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

      {/* Exibe cartão de erro quando houver mensagem */}
      {error && (
        <Card className="border-red-200 dark:border-red-800">
          <CardContent className="pt-6">
            <p className="text-red-600 dark:text-red-400">{error}</p>
          </CardContent>
        </Card>
      )}

      {/* Quando não houver concorrentes cadastrados */}
      {competitors.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-muted-foreground mb-4">Nenhum concorrente cadastrado ainda</p>
            <Button onClick={() => navigate('/products')}>Voltar aos Produtos</Button>
          </CardContent>
        </Card>
      ) : (
        // Lista de cartões, um por concorrente
        <div className="space-y-4">
          {competitors.map((competitor) => {
            // Cálculo simples de mudança de preço (placeholder).
            // Observação: lógica real deveria comparar com preço anterior salvo.
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
                        {/* Ícone e label indicando direção de preço (apenas visual neste momento) */}
                        {priceChange === 'stable' ? (
                          <TrendingDown className="h-4 w-4 text-green-600" />
                        ) : (
                          <TrendingUp className="h-4 w-4 text-red-600" />
                        )}
                        <span className="text-sm font-medium">Estável</span>
                      </div>
                    </div>
                  </div>

                  {/* Botão que abre o link do anúncio em nova aba */}
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
