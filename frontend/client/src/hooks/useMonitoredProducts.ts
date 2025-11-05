import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { MonitoredProduct, getMonitoredProducts } from '@/lib/api';

/**
 * Hook para gerenciar lista de produtos monitorados do usuário.
 *
 * - Faz a chamada ao endpoint que retorna os produtos monitorados.
 * - Expõe estado de carregamento, erro e função para refazer a requisição.
 * - Recarrega automaticamente quando o token de autenticação muda.
 */
export const useMonitoredProducts = () => {
  // Token JWT do contexto de autenticação (necessário para chamadas autenticadas)
  const { token } = useAuth();

  // Lista de produtos monitorados carregados da API
  const [products, setProducts] = useState<MonitoredProduct[]>([]);

  // Indicador de loading para UI (true enquanto a chamada estiver em andamento)
  const [isLoading, setIsLoading] = useState(false);

  // Mensagem de erro (em caso de falha na requisição)
  const [error, setError] = useState<string | null>(null);

  /**
   * Função que realiza a requisição para buscar os produtos monitorados.
   *
   * - Retorna imediatamente se não houver token (não autenticado).
   * - Atualiza estados de loading/erro/produtos conforme o resultado.
   * - Trata erros genéricos e instanciais de Error para obter a mensagem.
   */
  const fetchProducts = async () => {
    if (!token) {
      // Se não há token, não tentamos buscar dados
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const data = await getMonitoredProducts(token);
      // Atualiza lista com os dados retornados da API
      setProducts(data);
    } catch (err) {
      // Normaliza o erro para uma string legível na UI
      setError(err instanceof Error ? err.message : 'Erro ao buscar produtos');
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Efeito que dispara o carregamento inicial e sempre que o token mudar.
   * Útil para recarregar a lista quando o usuário faz login/logout.
   */
  useEffect(() => {
    fetchProducts();
  }, [token]);

  // API pública do hook: estados e função para refazer a requisição manualmente
  return { products, isLoading, error, refetch: fetchProducts };
};
