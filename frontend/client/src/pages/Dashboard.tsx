import React, { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useAlerts } from '@/hooks/useAlerts';
import { StatsCard } from '@/components/StatsCard';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/data-display/card';
import { Button } from '@/components/ui/button/button';
import { Alert, AlertDescription } from '@/components/ui/feedback/alert';
import { AlertTriangle, TrendingDown, CheckCircle, DollarSign, Zap } from 'lucide-react';
import { getDashboardStats } from '@/lib/api';
import { useLocation } from 'wouter';

// Componente principal do Dashboard
// - Responsável por buscar estatísticas do backend e exibir cards, alertas e ações rápidas.
export default function Dashboard() {
  // Token de autenticação obtido do contexto (usado nas chamadas à API)
  const { token } = useAuth();

  // Hook de roteamento (wouter) — navigate para redirecionamentos internos
  const [, navigate] = useLocation();

  // Hook customizado que retorna alertas do usuário
  const { alerts } = useAlerts();

  // Tipagem simples para o estado de estatísticas exibidas no dashboard
  const [stats, setStats] = useState({
    total_monitored: 0, // total de produtos monitorados
    active_alerts: 0,   // quantidade de alertas ativos
    ok_prices: 0,       // quantos preços estão OK/competitivos
    potential_adjustment: 0, // soma da economia potencial em reais
  });

  // Estado local para controlar carregamento (pode ser usado para skeletons/spinners)
  const [isLoading, setIsLoading] = useState(true);

  // Efeito que busca as estatísticas do dashboard quando o token estiver disponível
  useEffect(() => {
    if (!token) return; // se não houver token, não faz a requisição

    const fetchStats = async () => {
      try {
        // Chamada ao cliente API para obter dados do dashboard
        const data = await getDashboardStats(token);
        setStats(data); // atualiza estado com dados recebidos
      } catch (error) {
        // Log de erro estruturado — evitar exposição de segredos
        console.error('Erro ao buscar estatísticas:', error);
      } finally {
        // Sempre desabilita loading mesmo em erro
        setIsLoading(false);
      }
    };

    fetchStats();
  }, [token]);

  // Seleciona alertas recentes, priorizando falhas para dar visibilidade imediata
  const failedAlerts = alerts.filter((alert) => !alert.success).slice(0, 5);
  const recentAlerts = failedAlerts.length > 0 ? failedAlerts : alerts.slice(0, 5);

  return (
    <div className="space-y-6">
      {/* Seção de cabeçalho do Dashboard */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground mt-2">Visão geral do seu monitoramento de preços</p>
      </div>

      {/* Cards de Estatísticas — mostram KPIs principais */}
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
          // Muda o estilo do card quando há alertas ativos
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
          // Formata o valor em moeda BRL (string simples aqui, processamento pode ser movido para util)
          value={`R$ ${stats.potential_adjustment.toFixed(2)}`}
          subtitle="Se ajustar preços"
          icon={DollarSign}
          variant="warning"
        />
      </div>

      {/* Alertas Recentes — prioriza falhas para orientar ações futuras */}
      {recentAlerts.length > 0 && (
        <Card className="border-red-200 dark:border-red-800">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-orange-500" />
              Últimos Alertas
            </CardTitle>
            <CardDescription>
              {failedAlerts.length > 0
                ? 'Falhas de envio ou regras que exigem acompanhamento atento'
                : 'Histórico recente das notificações enviadas'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {recentAlerts.map((alert) => {
              const Icon = alert.success ? CheckCircle : AlertTriangle;

              return (
                // Cada alerta renderizado com ícone e descrição — chave baseada em alert.id
                <Alert key={alert.id} className="bg-orange-50 dark:bg-orange-950 border-orange-200 dark:border-orange-800">
                  <Icon className={`h-4 w-4 ${alert.success ? 'text-green-600' : 'text-orange-600'}`} />
                  <AlertDescription className="text-orange-800 dark:text-orange-200">
                    <span className="font-medium block">
                      {alert.subject || alert.message}
                    </span>
                    <span className="text-sm opacity-80 block">
                      {new Date(alert.sent_at).toLocaleString('pt-BR')}
                    </span>
                  </AlertDescription>
                </Alert>
              );
            })}
            {/* Botão que leva à lista completa de alertas */}
            <Button variant="outline" className="w-full" onClick={() => navigate('/alerts')}>
              Ver todos os alertas
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Ações Rápidas — atalhos para telas comuns */}
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
