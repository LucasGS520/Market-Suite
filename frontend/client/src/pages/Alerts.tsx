import React from 'react';
import { useAlerts } from '@/hooks/useAlerts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/data-display/card';
import { Badge } from '@/components/ui/data-display/badge';
import { AlertCircle, AlertTriangle, CheckCircle } from 'lucide-react';
import { Skeleton } from '@/components/ui/data-display/skeleton';
import { Alert as FeedbackAlert, AlertDescription, AlertTitle } from '@/components/ui/feedback/alert';

/**
 * Componente de página que lista alertas do usuário.
 *
 * - Exibe estado de carregamento com skeletons.
 * - Lista logs de notificações retornados pela API.
 * - Indica que o histórico é somente leitura até que o backend permita mutações.
 */
export default function Alerts() {
  // Hook personalizado que encapsula fetch, mutações e estado dos alerts
  const { alerts, isLoading, error } = useAlerts();

  // Estado de carregamento: mostra skeletons para indicar carregamento de dados
  if (isLoading) {
    return (
      <div className="space-y-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Alertas</h1>
        </div>
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="pt-6">
                {/* Placeholder visual enquanto os dados carregam */}
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
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Alertas</h1>
        {/* Informativo sobre o estado atual das ações disponíveis */}
        <p className="text-muted-foreground mt-2">
          Histórico de notificações enviado pelo backend. Esta lista é somente leitura até disponibilizarmos ações de gestão.
        </p>
      </div>

      {error && (
        <FeedbackAlert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Erro ao carregar alertas</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </FeedbackAlert>
      )}

      {alerts.length === 0 ? (
        // Estado vazio: nenhum alerta disponível
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-muted-foreground">Nenhum alerta no momento</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {alerts.map((alert) => {
            const Icon = alert.success ? CheckCircle : AlertTriangle;
            const badgeVariant = alert.success ? 'secondary' : 'destructive';
            const badgeLabel = alert.success ? 'Enviado' : 'Falha';

            return (
              <Card key={alert.id} className={!alert.success ? 'border-red-200 dark:border-red-800' : ''}>
                <CardContent className="pt-6">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="flex flex-1 gap-3">
                      <Icon
                        className={`h-5 w-5 flex-shrink-0 mt-0.5 ${
                          alert.success ? 'text-green-600' : 'text-red-600'
                        }`}
                      />
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-medium">{alert.subject || alert.message}</p>
                          <Badge variant={badgeVariant}>{badgeLabel}</Badge>
                          <Badge variant="outline">{alert.channel}</Badge>
                        </div>
                        <p className="text-sm text-muted-foreground whitespace-pre-line">{alert.message}</p>
                        {alert.error && !alert.success && (
                          <p className="text-sm text-destructive">
                            Erro reportado: {alert.error}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="text-sm text-muted-foreground text-right sm:text-left">
                      {new Date(alert.sent_at).toLocaleString('pt-BR')}
                    </div>
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
