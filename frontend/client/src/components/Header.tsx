import React from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useLocation } from 'wouter';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Bell, Settings, LogOut, User } from 'lucide-react';
import { APP_LOGO, APP_TITLE } from '@/const';

/**
 * Componente de header com navegação e menu de usuário.
 * Exibe logo, título, atalho para notificações e menu de usuário (configurações / sair).
 * Utiliza contexto de autenticação para mostrar email e realizar logout.
 */
export const Header: React.FC = () => {
  // Hooks: obtem usuário e função de logout do contexto de autenticação
  const { user, logout } = useAuth();
  // Hook de navegação do wouter (navegar para rotas internas)
  const [, navigate] = useLocation();

  // Realiza logout e redireciona para a tela de login
  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    // Header fixo no topo com borda inferior e efeito de backdrop
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-16 items-center justify-between">
        {/* Logo e título: ao clicar navega para a página inicial */}
        <div
          className="flex items-center gap-3 cursor-pointer"
          onClick={() => navigate('/')}
          role="button"
          aria-label="Ir para página inicial"
        >
          <img src={APP_LOGO} alt={APP_TITLE} className="h-8 w-8" />
          <span className="text-lg font-bold text-orange-500">{APP_TITLE}</span>
          {/* Descrição curta do produto */}
          <span className="text-xs text-muted-foreground">Monitoramento Inteligente de Preços</span>
        </div>

        {/* Área à direita: notificações + menu do usuário */}
        <div className="flex items-center gap-4">
          {/* Botão de notificações: navega para /alerts */}
          <Button variant="ghost" size="icon" onClick={() => navigate('/alerts')} aria-label="Notificações">
            <Bell className="h-5 w-5" />
          </Button>

          {/* Menu de usuário: trigger com ícone e conteúdo alinhado à direita */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Abrir menu do usuário">
                <User className="h-5 w-5" />
              </Button>
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end">
              {/* Mostra o email do usuário quando disponível */}
              <div className="px-2 py-1.5 text-sm font-medium">{user?.email ?? 'Usuário'}</div>

              {/* Item: configurações -> navega para /settings */}
              <DropdownMenuItem onClick={() => navigate('/settings')}>
                <Settings className="mr-2 h-4 w-4" />
                Configurações
              </DropdownMenuItem>

              {/* Item: efetua logout e redireciona */}
              <DropdownMenuItem onClick={handleLogout}>
                <LogOut className="mr-2 h-4 w-4" />
                Sair
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
};
