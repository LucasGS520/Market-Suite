// Componente de página que lista concorrentes de um produto monitorado.
// Contém carregamento, tratamento de erro e ações para abrir o anúncio do concorrente.

import React, { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useLocation } from 'wouter';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/data-display/card';
import { Button } from '@/components/ui/button/button';
import { Badge } from '@/components/ui/data-display/badge';
import { ArrowLeft, TrendingDown, TrendingUp, ExternalLink, RotateCcw } from 'lucide-react';
import { Skeleton } from '@/components/ui/data-display/skeleton';
import { getCompetitors, Competitor, runComparison, PriceComparison, PriceDiscrepancy, PriceComparisonAlert } from '@/lib/api';

type UiCompetitor = {
  id: string;
  name: string;
  productUrl: string;
  currentPrice: number | null;
  lastChecked: Date | null;
  status: Competitor['status'];
};

/**
 * Converte um concorrente recebido da API para a estrutura exibida na UI.
 */
const mapCompetitorToUi = (competitor: Competitor): UiCompetitor => {
  const hasCurrentPrice = competitor.current_price !== null && competitor.current_price !== undefined;
  const parsedPrice = hasCurrentPrice ? Number(competitor.current_price) : null;
  const currentPrice = parsedPrice !== null && Number.isFinite(parsedPrice) ? parsedPrice : null;

  return {
    id: competitor.id,
    name: competitor.name_competitor,
    productUrl: competitor.product_url,
    currentPrice,
    lastChecked: competitor.last_checked ? new Date(competitor.last_checked) : null,
    status: competitor.status,
  };
};

export default function Competitors() {
  // Recupera token do contexto de autenticação
  const { token } = useAuth();

  // Hook do roteamento (wouter): location atual e função de navegação
  const [location, navigate] = useLocation();

  // Estado local: lista de concorrentes
  const [competitors, setCompetitors] = useState<UiCompetitor[]>([]);
  // Estado de carregamento para mostrar skeletons enquanto busca dados
  const [isLoading, setIsLoading] = useState(true);
  // Mensagem de erro simples para exibição em UI
  const [error, setError] = useState<string | null>(null);
  // Estado derivado ao executar a comparação manualmente
  const [comparison, setComparison] = useState<PriceComparison | null>(null);
  const [isRunningComparison, setIsRunningComparison] = useState(false);
  const [comparisonError, setComparisonError] = useState<string | null>(null);

  // Extraindo o ID do produto da URL (assume que o ID vem como última parte da rota)
  const productId = location.split('/').pop() || '';

  useEffect(() => {
    // Só tenta buscar se tivermos token e productId válidos
    if (!token || !productId) return;

    const fetchCompetitors = async () => {
      try {
        // Chamada ao client API que retorna a lista de concorrentes
        const data = await getCompetitors(token, productId);
        const normalizedCompetitors = data.map(mapCompetitorToUi);
        setCompetitors(normalizedCompetitors);
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

  /**
   * Dispara a comparação manual e guarda o payload completo retornado pela API
   */
  const handleRunComparison = async () => {
    if (!token || !productId) {
      return;
    }

    setIsRunningComparison(true);
    setComparisonError(null);

    try {
      // Limpa dados anteriores para evitar mostrar resultado antigo enquanto carrega
      setComparison(null);
      const payload = await runComparison(token, productId);
      setComparison(payload);
    } catch (err) {
      setComparisonError(err instanceof Error ? err.message : 'Erro ao executar comparação');
    } finally {
      setIsRunningComparison(false);
    }
  };

  /**
   * Formata valores monetários respeitando null/undefined.
   */
  const formatCurrency = (value: number | null | undefined): string => {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return 'Valor indisponível';
    }

    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
      minimumFractionDigits: 2,
    }).format(value);
  };

  /**
   * Formata percentuais com fallback claro
   */
  const formatPercentage = (value: number | null | undefined): string => {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return '-';
    }

    return `${value.toFixed(2)}%`;
  };

  /**
   * Renderiza o bloco de discrepâncias detalhadas
   */
  const renderDiscrepancy = (label: string, discrepancy: PriceDiscrepancy | null) => {
    if (!discrepancy) {
      return (
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-sm">Sem dados disponíveis</p>
        </div>
      );
    }

    return (
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-sm font-medium">{discrepancy.name}</p>
        <p className="text-xs text-muted-foreground">Preço: {formatCurrency(discrepancy.price)}</p>
        <p className="text-xs text-muted-foreground">Δ vs alvo: {formatPercentage(discrepancy.pct_x_target)}</p>
        <p className="text-xs text-muted-foreground">Δ vs monitorado: {formatPercentage(discrepancy.pct_x_monitored)}</p>
      </div>
    );
  };

  /**
   * Normaliza descrição de alerta considerando campos opcionais
   */
  const describeAlert = (alert: PriceComparisonAlert, index: number) => {
    const baseLabel = alert.name ?? `Alerta ${index + 1}`;

    if (alert.status) {
      return `${baseLabel} - anúncio ${alert.status === 'unavailable' ? 'indisponível' : 'removido'}`;
    }

    if (alert.type && alert.change !== undefined) {
      const direction = alert.type === 'price_increase' ? 'Aumento' : 'Redução';
      return `${baseLabel} - ${direction} de ${formatCurrency(alert.change)} (${formatPercentage(alert.pct_change ?? null)})`;
    }

    if (alert.pct_below_target !== undefined) {
      return `${baseLabel} - ${formatCurrency(alert.price ?? null)} (${formatPercentage(alert.pct_below_target)} abaixo da meta)`;
    }

    return baseLabel;
  };

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
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={() => navigate('/products')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Concorrentes</h1>
            <p className="text-muted-foreground mt-2">{competitors.length} concorrentes encontrados</p>
          </div>
        </div>

        <Button onClick={handleRunComparison} disabled={isRunningComparison} className="gap-2" variant="outline" type="button">
          <RotateCcw className={`h-4 w-4 ${isRunningComparison ? 'animate-spin' : ''}`} />
          {isRunningComparison ? 'Executando comparação...' : 'Executar comparação agora'}
        </Button>
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
            const priceChange = competitor.currentPrice !== null && competitor.currentPrice > 0 ? 'stable' : 'unknown';

            return (
              <Card key={competitor.id}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <CardTitle className="text-lg">{competitor.name}</CardTitle>
                      <p className="text-sm text-muted-foreground mt-1">
                        Última atualização:{' '}
                        {competitor.lastChecked ? competitor.lastChecked.toLocaleDateString('pt-BR') : 'Sem registro'}
                      </p>
                    </div>
                    <Badge variant="outline">Concorrente</Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-muted-foreground">Preço</p>
                      <p className="text-2xl font-bold">
                        {competitor.currentPrice !== null ? `R$ ${competitor.currentPrice.toFixed(2)}` : 'Preço indisponível'}
                      </p>
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
                    onClick={() => window.open(competitor.productUrl, '_blank')}
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

      {comparisonError && (
        <Card className="border-red-200 dark:border-red-800">
          <CardContent className="pt-6 text-red-600 dark:text-red-400">
            {comparisonError}
          </CardContent>
        </Card>
      )}

      {comparison && (
        <Card>
          <CardHeader>
            <CardTitle>Resultado da comparação mais recente</CardTitle>
            <CardDescription>
              {`Preço monitorado: ${formatCurrency(comparison.monitored_price)} | Preço alvo: ${formatCurrency(comparison.target_price)}`}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <p className="text-xs text-muted-foreground">Média dos concorrentes</p>
                <p className="text-lg font-semibold">{formatCurrency(comparison.average_competitor_price)}</p>
              </div>
              {renderDiscrepancy('Menor preço', comparison.lowest_competitor)}
              {renderDiscrepancy('Maior preço', comparison.highest_competitor)}
            </div>

            <div className="space-y-2">
              <h3 className="text-base font-semibold">Discrepâncias detalhadas</h3>
              {comparison.discrepancies.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhum concorrente com preço válido.</p>
              ) : (
                <div className="space-y-3">
                  {comparison.discrepancies.map((item) => (
                    <div key={item.competitor_id} className="rounded-md border p-3">
                      <p className="text-sm font-medium">{item.name}</p>
                      <p className="text-xs text-muted-foreground">Preço: {formatCurrency(item.price)}</p>
                      <p className="text-xs text-muted-foreground">Δ vs menor: {formatCurrency(item.delta_x_min_competitor)}</p>
                      <p className="text-xs text-muted-foreground">Δ vs monitorado: {formatCurrency(item.delta_x_monitored)}</p>
                      <p className="text-xs text-muted-foreground">Variação vs alvo: {formatPercentage(item.pct_x_target)}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-2">
              <h3 className="text-base font-semibold">Alertas emitidos</h3>
              {comparison.alerts.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhum alerta gerado.</p>
              ) : (
                <ul className="list-disc space-y-1 pl-5 text-sm">
                  {comparison.alerts.map((alert, index) => (
                    <li key={`${alert.competitor_id ?? alert.product_id ?? index}`}>{describeAlert(alert, index)}</li>
                  ))}
                </ul>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
