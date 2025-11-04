import React from 'react';
import { useLocation } from 'wouter';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { BarChart3, ShoppingCart, Plus } from 'lucide-react';

/**
 * Componente de navegação com abas
 */
export const Navigation: React.FC = () => {
  const [location, navigate] = useLocation();

  // Determinando a aba ativa baseado na URL
  const getActiveTab = () => {
    if (location === '/') return 'dashboard';
    if (location === '/products') return 'products';
    if (location === '/add') return 'add';
    return 'dashboard';
  };

  const handleTabChange = (value: string) => {
    switch (value) {
      case 'dashboard':
        navigate('/');
        break;
      case 'products':
        navigate('/products');
        break;
      case 'add':
        navigate('/add');
        break;
    }
  };

  return (
    <div className="border-b bg-background">
      <div className="container">
        <Tabs value={getActiveTab()} onValueChange={handleTabChange} className="w-full">
          <TabsList className="grid w-full grid-cols-3 bg-transparent">
            <TabsTrigger value="dashboard" className="gap-2">
              <BarChart3 className="h-4 w-4" />
              <span className="hidden sm:inline">Dashboard</span>
            </TabsTrigger>
            <TabsTrigger value="products" className="gap-2">
              <ShoppingCart className="h-4 w-4" />
              <span className="hidden sm:inline">Produtos</span>
            </TabsTrigger>
            <TabsTrigger value="add" className="gap-2">
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">Adicionar</span>
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
    </div>
  );
};
