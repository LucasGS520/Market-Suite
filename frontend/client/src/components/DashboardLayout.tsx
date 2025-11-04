import React from 'react';
import { Header } from './Header';
import { Navigation } from './Navigation';

interface DashboardLayoutProps {
  children: React.ReactNode;
}

/**
 * Layout principal para páginas autenticadas
 */
export const DashboardLayout: React.FC<DashboardLayoutProps> = ({ children }) => {
  return (
    <div className="min-h-screen flex flex-col bg-background">
      <Header />
      <Navigation />
      <main className="flex-1 container py-6">
        {children}
      </main>
    </div>
  );
};
