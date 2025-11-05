import React from 'react';
import { useAlerts } from '@/hooks/useAlerts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/data-display/card';
import { Button } from '@/components/ui/button/button';
import { Badge } from '@/components/ui/data-display/badge';
import { AlertTriangle, Trash2, CheckCircle } from 'lucide-react';
import { Skeleton } from '@/components/ui/data-display/skeleton';

/**
 * Componente de página que lista alertas do usuário.
 *
 * - Exibe estado de carregamento com skeletons.
 * - Separa alertas em não lidos e lidos.
 * - Permite marcar como lido e deletar alertas via hooks.
 */
export default function Alerts() {
  // Hook personalizado que encapsula fetch, mutações e estado dos alerts
  const { alerts, isLoading, markAsRead, deleteAlert } = useAlerts();

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

  // Agrupa alertas em não lidos e lidos para renderização separada
  const unreadAlerts = alerts.filter((a) => !a.is_read);
  const readAlerts = alerts.filter((a) => a.is_read);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Alertas</h1>
        {/* Resumo rápido do número de alertas não lidos */}
        <p className="text-muted-foreground mt-2">
          {unreadAlerts.length} não lido{unreadAlerts.length !== 1 ? 's' : ''}
        </p>
      </div>

      {alerts.length === 0 ? (
        // Estado vazio: nenhum alerta disponível
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-muted-foreground">Nenhum alerta no momento</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          {/* Alertas não lidos */}
          {unreadAlerts.length > 0 && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Não Lidos</h2>
              {unreadAlerts.map((alert) => (
                <Card key={alert.id} className="border-orange-200 dark:border-orange-800 bg-orange-50 dark:bg-orange-950">
                  <CardContent className="pt-6">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 flex gap-3">
                        {/* Ícone indicando alerta importante */}
                        <AlertTriangle className="h-5 w-5 text-orange-600 flex-shrink-0 mt-0.5" />
                        <div>
                          {/* Mensagem do alerta */}
                          <p className="font-medium">{alert.message}</p>
                          {/* Data formatada para pt-BR */}
                          <p className="text-sm text-muted-foreground mt-1">
                            {new Date(alert.created_at).toLocaleDateString('pt-BR')}
                          </p>
                        </div>
                      </div>

                      {/* Ações rápidas: marcar como lido e deletar */}
                      <div className="flex gap-2 flex-shrink-0">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => markAsRead(alert.id)} // Chama ação do hook para marcar como lido
                        >
                          <CheckCircle className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => deleteAlert(alert.id)} // Chama ação do hook para deletar alerta
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {/* Alertas lidos */}
          {readAlerts.length > 0 && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Lidos</h2>
              {readAlerts.map((alert) => (
                <Card key={alert.id} className="opacity-75">
                  <CardContent className="pt-6">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 flex gap-3">
                        {/* Ícone indicando status lido */}
                        <CheckCircle className="h-5 w-5 text-green-600 flex-shrink-0 mt-0.5" />
                        <div>
                          {/* Mensagem do alerta com estilo atenuado */}
                          <p className="font-medium text-muted-foreground">{alert.message}</p>
                          {/* Data do alerta */}
                          <p className="text-sm text-muted-foreground mt-1">
                            {new Date(alert.created_at).toLocaleDateString('pt-BR')}
                          </p>
                        </div>
                      </div>

                      {/* Ação de deletar para alertas já lidos */}
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => deleteAlert(alert.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
