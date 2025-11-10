import React from 'react';
import { useMonitoredProducts } from '@/hooks/useMonitoredProducts';
import { useLocation } from 'wouter';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/data-display/card';
import { Button } from '@/components/ui/button/button';
import { Badge } from '@/components/ui/data-display/badge';
import { TrendingUp, ExternalLink, AlertCircle, RotateCcw } from 'lucide-react';
import { Skeleton } from '@/components/ui/data-display/skeleton';
import type { MonitoredStatus } from '@/lib/api';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/feedback/alert';
import { format } from 'path';

/**
 * Products.tsx
 * Componente de listagem de produtos monitorados.
 * - Busca produtos via hook personalizado `useMonitoredProducts`
 * - Mostra skeletons enquanto carrega
 * - Permite navegar para adicionar produto ou ver concorrentes
 */

/**
 * Mapeia o enum de status para rótulo exibido e estilo visual
 */
const statusDisplayConfig: Record<
  MonitoredStatus,
  { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline'; highlight?: boolean }
> = {
  active: { label: 'Ativo', variant: 'default' },
  inactive: { label: 'Inativo', variant: 'secondary'},
  pending: { label: 'Agendado', variant: 'outline' },
  failed: { label: 'Falha', variant: 'destructive', highlight: true },
};

/** Configuração fallback para futuros status desconhecidos */
const unknownStatusDisplay = { label: 'Desconhecido', variant: 'outline' as const };

/** 
 * Formata valores numéricos em moeda brasileira tratando dados ausentes
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
 * Descreve a data/hora da última coleta considerando payloads sem informação
 */
const describeLastChecked = (timestamp: string | null | undefined): string => {
  if (!timestamp) {
    return 'Nenhuma coleta registrada';
  }

  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return 'Data inválida';
  }

  return parsed.toLocaleString('pt-BR');
};

/** Componente principal que renderiza a lista de produtos monitorados */
export default function Products() {
  // Hook que retorna os produtos, estado de carregamento e erro da API
  const { products, isLoading, error, refetch } = useMonitoredProducts();

  // Hook do wouter para navegação (navigate)
  const [, navigate] = useLocation();

  /**
   * Acionador manual para tentar novamente a busca de produtos.
   * Mantido inline para evitar recriações denecessárias e facilitar o binding no botão.
   */
  const handleRetry = () => {
    refetch();
  };

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

      {error && (
        // Alertamos falha de carregamento antes de avaliar estados vazios para orientar ações imediatas
        <Alert variant="destructive" className="items-start">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Erro ao carregar produtos</AlertTitle>
          <AlertDescription className="space-y-3">
            <p>{error}</p>
            <Button variant="outline" size="sm" onClick={handleRetry} className="gap-2" type="button">
              <RotateCcw className="h-4 w-4" />
              Tentar Novamente
            </Button>
          </AlertDescription>
        </Alert>
      )}

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
          {products.map((product) => {
            const statusInfo = statusDisplayConfig[product.status] ?? unknownStatusDisplay;
            const showCompetitors = product.competitors_count !== undefined && product.competitors_count !== null;
            const infoGridCols = `grid grid-cols-1 gap-4 sm:grid-cols-2 ${showCompetitors ? 'lg:grid-cols-3' : ''}`;
            const highlightBorder = statusInfo.highlight ? 'border-red-200 dark:border-red-800' : '';
            
            return (
              <Card key={product.id} className={highlightBorder}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      {/* Identificação do produto com fallback para ausência de nome */}
                      <CardTitle className="text-lg">
                        {product.name_identification ?? 'Produto sem identificação'}
                      </CardTitle>
                      {/* Data da última atualização considerando payloads nulos */}
                      <p className="text-sm text-muted-foreground mt-1">
                        Última atualização: {describeLastChecked(product.last_checked)}
                      </p>
                    </div>

                    {/* Badge traduzindo o enum do backend para rótulos em português */}
                    <Badge variant={statusInfo.variant}>{statusInfo.label}</Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className={infoGridCols}>
                    {/* Exibe preço atual retornado pelo scraping/API com tratamento de vazio */}
                    <div>
                      <p className="text-xs text-muted-foreground">Seu Preço</p>
                      <p className="text-xl font-bold">{formatCurrency(product.current_price)}</p>
                    </div>

                    {/* Número de concorrentes monitorados quando a API fornecer a métrica */}
                    {showCompetitors && (
                      <div>
                        <p className="text-xs text-muted-foreground">Concorrentes</p>
                        <p className="text-xl font-bold">{product.competitors_count}</p>
                      </div>
                    )}
                  </div>

                  {product.status === 'pending' && (
                    <p className="text-sm text-muted-foreground">
                      Coleta inicial agendada. Atualize a página em alguns minutos para ver os preços.
                    </p>
                  )}

                  <div className="flex gap-2 pt-2">
                    {/* Abre o anúncio original em nova aba apenas quando a URL estiver disponível */}
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      disabled={!product.product_url}
                      onClick={() => product.product_url && window.open(product.product_url, '_blank')}
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
            );
          })}
        </div>
      )}
    </div>
  );
}
