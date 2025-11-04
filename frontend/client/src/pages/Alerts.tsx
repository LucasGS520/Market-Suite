import React from 'react';
import { useAlerts } from '@/hooks/useAlerts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/data-display/card';
import { Button } from '@/components/ui/button/button';
import { Badge } from '@/components/ui/data-display/badge';
import { AlertTriangle, Trash2, CheckCircle } from 'lucide-react';
import { Skeleton } from '@/components/ui/data-display/skeleton';

export default function Alerts() {
  const { alerts, isLoading, markAsRead, deleteAlert } = useAlerts();

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
                <Skeleton className="h-20 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  const unreadAlerts = alerts.filter((a) => !a.is_read);
  const readAlerts = alerts.filter((a) => a.is_read);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Alertas</h1>
        <p className="text-muted-foreground mt-2">
          {unreadAlerts.length} não lido{unreadAlerts.length !== 1 ? 's' : ''}
        </p>
      </div>

      {alerts.length === 0 ? (
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
                        <AlertTriangle className="h-5 w-5 text-orange-600 flex-shrink-0 mt-0.5" />
                        <div>
                          <p className="font-medium">{alert.message}</p>
                          <p className="text-sm text-muted-foreground mt-1">
                            {new Date(alert.created_at).toLocaleDateString('pt-BR')}
                          </p>
                        </div>
                      </div>
                      <div className="flex gap-2 flex-shrink-0">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => markAsRead(alert.id)}
                        >
                          <CheckCircle className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => deleteAlert(alert.id)}
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
                        <CheckCircle className="h-5 w-5 text-green-600 flex-shrink-0 mt-0.5" />
                        <div>
                          <p className="font-medium text-muted-foreground">{alert.message}</p>
                          <p className="text-sm text-muted-foreground mt-1">
                            {new Date(alert.created_at).toLocaleDateString('pt-BR')}
                          </p>
                        </div>
                      </div>
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
