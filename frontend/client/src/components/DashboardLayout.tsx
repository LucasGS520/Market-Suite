import React from 'react';
import { Header } from './Header';
import { Navigation } from './Navigation';

// Componente de layout principal usado em páginas que exigem autenticação.
// Agrupa Header, Navigation e a área principal onde o conteúdo (children) é renderizado.

/**
 * Props do DashboardLayout
 * @property children - Conteúdo a ser exibido na área principal do layout
 */
interface DashboardLayoutProps {
  children: React.ReactNode;
}

/**
 * Layout principal para páginas autenticadas.
 * Renderiza o cabeçalho, a navegação e a área central onde o conteúdo da página é exibido.
 */
export const DashboardLayout: React.FC<DashboardLayoutProps> = ({ children }) => {
  return (
    // Container que garante altura mínima da tela e estrutura em coluna
    <div className="min-h-screen flex flex-col bg-background">
      {/* Cabeçalho fixo no topo da aplicação */}
      <Header />

      {/* Componente de navegação (barra lateral ou topo, dependendo do layout) */}
      <Navigation />

      {/* Área principal de conteúdo com espaçamento vertical (py-6) */}
      <main className="flex-1 container py-6">
        {children}
      </main>
    </div>
  );
};
