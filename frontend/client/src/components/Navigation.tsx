import React from 'react';
import { useLocation } from 'wouter';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { BarChart3, ShoppingCart, Plus } from 'lucide-react';

/**
 * Componente de navegação principal com abas responsivas.
 * - Sincroniza a aba ativa com a rota via `wouter`.
 * - Ao alterar a aba, navega para a rota correspondente.
 */
export const Navigation: React.FC = () => {
  // Location atual e função de navegação fornecidas pelo hook `wouter`.
  const [location, navigate] = useLocation();

  // Calcula a aba ativa a partir da URL atual (memorizado para evitar recomputações).
  const activeTab = React.useMemo<"dashboard" | "products" | "add">(() => {
    if (location === '/') return 'dashboard';
    if (location === '/products') return 'products';
    if (location === '/add') return 'add';
    // Valor padrão caso a rota não corresponda a nenhuma aba conhecida.
    return 'dashboard';
  }, [location]);

  /**
   * Manipula a troca de aba (disparada pelo componente Tabs).
   * Faz a navegação para a rota correspondente ao valor selecionado.
   * @param value - valor da aba selecionada ('dashboard' | 'products' | 'add')
   */
  const handleTabChange = (value: string): void => {
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
      default:
        // Ignora valores desconhecidos para manter a robustez.
        break;
    }
  };

  return (
    <div className="border-b bg-background">
      <div className="container">
        {/* Componente de Tabs: value controla a aba ativa */}
        <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
          {/* Lista de triggers: 3 colunas para cada aba */}
          <TabsList className="grid w-full grid-cols-3 bg-transparent">
            <TabsTrigger value="dashboard" className="gap-2">
              {/* Ícone da aba */}
              <BarChart3 className="h-4 w-4" />
              {/* Rótulo oculto em telas muito pequenas */}
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
