import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { MonitoredProduct, getMonitoredProducts } from '@/lib/api';

/**
 * Hook para gerenciar produtos monitorados
 */
export const useMonitoredProducts = () => {
  const { token } = useAuth();
  const [products, setProducts] = useState<MonitoredProduct[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchProducts = async () => {
    if (!token) return;

    setIsLoading(true);
    setError(null);

    try {
      const data = await getMonitoredProducts(token);
      setProducts(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao buscar produtos');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchProducts();
  }, [token]);

  return { products, isLoading, error, refetch: fetchProducts };
};
