import React from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useLocation } from 'wouter';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Bell, Settings, LogOut, User } from 'lucide-react';
import { APP_LOGO, APP_TITLE } from '@/const';

/**
 * Componente de header com navegação e menu de usuário
 */
export const Header: React.FC = () => {
  const { user, logout } = useAuth();
  const [, navigate] = useLocation();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-16 items-center justify-between">
        {/* Logo e Título */}
        <div className="flex items-center gap-3 cursor-pointer" onClick={() => navigate('/')}>
          <img src={APP_LOGO} alt={APP_TITLE} className="h-8 w-8" />
          <span className="text-lg font-bold text-orange-500">{APP_TITLE}</span>
          <span className="text-xs text-muted-foreground">Monitoramento Inteligente de Preços</span>
        </div>

        {/* Menu de Usuário */}
        <div className="flex items-center gap-4">
          {/* Notificações */}
          <Button variant="ghost" size="icon" onClick={() => navigate('/alerts')}>
            <Bell className="h-5 w-5" />
          </Button>

          {/* Menu de Usuário */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon">
                <User className="h-5 w-5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <div className="px-2 py-1.5 text-sm font-medium">{user?.email}</div>
              <DropdownMenuItem onClick={() => navigate('/settings')}>
                <Settings className="mr-2 h-4 w-4" />
                Configurações
              </DropdownMenuItem>
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
