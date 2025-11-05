import React from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useLocation } from 'wouter';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/data-display/card';
import { Button } from '@/components/ui/button/button';
import { LogOut, User, Bell } from 'lucide-react';

// Página de configurações do usuário.
// Contém seções para perfil, notificações, segurança e informações sobre o app.
export default function Settings() {
  // Obtém dados do usuário e ação de logout a partir do AuthContext
  const { user, logout } = useAuth();
  // useLocation retorna [location, navigate]; usamos apenas navigate para redirecionar
  const [, navigate] = useLocation();

  // Handler responsável por encerrar a sessão e redirecionar para a tela de login
  const handleLogout = () => {
    logout(); // limpa sessão/estado de autenticação
    navigate('/login'); // redireciona o usuário para a rota de login
  };

  return (
    <div className="space-y-6">
      {/* Cabeçalho da página */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Configurações</h1>
        <p className="text-muted-foreground mt-2">Gerencie suas preferências e conta</p>
      </div>

      {/* Perfil do Usuário: exibe email e nome (quando disponível) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <User className="h-5 w-5" />
            Perfil
          </CardTitle>
          <CardDescription>Informações da sua conta</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium">Email</label>
            <p className="text-sm text-muted-foreground mt-1">{user?.email}</p>
          </div>
          {user?.name && (
            <div>
              <label className="text-sm font-medium">Nome</label>
              <p className="text-sm text-muted-foreground mt-1">{user.name}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Notificações: placeholder informativo enquanto a funcionalidade é desenvolvida */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bell className="h-5 w-5" />
            Notificações
          </CardTitle>
          <CardDescription>Configure suas preferências de notificação</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Funcionalidade de notificações em desenvolvimento
          </p>
        </CardContent>
      </Card>

      {/* Segurança: opção de encerrar sessão (logout) do usuário */}
      <Card>
        <CardHeader>
          <CardTitle>Segurança</CardTitle>
          <CardDescription>Gerencie sua segurança e sessões</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-sm font-medium mb-3">Sair da Conta</p>
            <Button variant="destructive" onClick={handleLogout} className="w-full">
              <LogOut className="mr-2 h-4 w-4" />
              Sair
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Sobre: informações de versão e descrição curta do produto */}
      <Card>
        <CardHeader>
          <CardTitle>Sobre</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>MarketAlert v1.0.0</p>
          <p>Monitoramento Inteligente de Preços</p>
        </CardContent>
      </Card>
    </div>
  );
}
