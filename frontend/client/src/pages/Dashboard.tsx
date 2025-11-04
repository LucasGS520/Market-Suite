import React, { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useAlerts } from '@/hooks/useAlerts';
import { StatsCard } from '@/components/StatsCard';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AlertTriangle, TrendingDown, CheckCircle, DollarSign, Zap } from 'lucide-react';
import { getDashboardStats } from '@/lib/api';
import { useLocation } from 'wouter';

export default function Dashboard() {
  const { token } = useAuth();
  const [, navigate] = useLocation();
  const { alerts } = useAlerts();
  const [stats, setStats] = useState({
    total_monitored: 0,
    active_alerts: 0,
    ok_prices: 0,
    potential_savings: 0,
  });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!token) return;

    const fetchStats = async () => {
      try {
        const data = await getDashboardStats(token);
        setStats(data);
      } catch (error) {
        console.error('Erro ao buscar estatísticas:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchStats();
  }, [token]);

  const urgentAlerts = alerts.filter(a => !a.is_read).slice(0, 5);

  return (
    <div className="space-y-6">
      {/* Seção de Estatísticas */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground mt-2">Visão geral do seu monitoramento de preços</p>
      </div>

      {/* Cards de Estatísticas */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatsCard
          title="Total de Produtos"
          value={stats.total_monitored}
          subtitle="Monitorados ativamente"
          icon={TrendingDown}
          variant="default"
        />
        <StatsCard
          title="Alertas Ativos"
          value={stats.active_alerts}
          subtitle="Requerem atenção"
          icon={AlertTriangle}
          variant={stats.active_alerts > 0 ? 'alert' : 'default'}
        />
        <StatsCard
          title="Preços OK"
          value={stats.ok_prices}
          subtitle="Competitivos"
          icon={CheckCircle}
          variant="success"
        />
        <StatsCard
          title="Economia Potencial"
          value={`R$ ${stats.potential_savings.toFixed(2)}`}
          subtitle="Se ajustar preços"
          icon={DollarSign}
          variant="warning"
        />
      </div>

      {/* Alertas Urgentes */}
      {urgentAlerts.length > 0 && (
        <Card className="border-red-200 dark:border-red-800">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-orange-500" />
              Alertas Urgentes
            </CardTitle>
            <CardDescription>Ações recomendadas para seus produtos</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {urgentAlerts.map((alert) => (
              <Alert key={alert.id} className="bg-orange-50 dark:bg-orange-950 border-orange-200 dark:border-orange-800">
                <AlertTriangle className="h-4 w-4 text-orange-600" />
                <AlertDescription className="text-orange-800 dark:text-orange-200">
                  {alert.message}
                </AlertDescription>
              </Alert>
            ))}
            <Button variant="outline" className="w-full" onClick={() => navigate('/alerts')}>
              Ver todos os alertas
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Ações Rápidas */}
      <Card>
        <CardHeader>
          <CardTitle>Ações Rápidas</CardTitle>
        </CardHeader>
        <CardContent className="flex gap-3 flex-wrap">
          <Button onClick={() => navigate('/products')}>Ver Produtos</Button>
          <Button variant="outline" onClick={() => navigate('/add')}>
            Adicionar Produto
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
