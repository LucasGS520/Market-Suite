import React, { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useLocation } from 'wouter';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/data-display/card';
import { Button } from '@/components/ui/button/button';
import { Input } from '@/components/ui/inputs/input';
import { Alert, AlertDescription } from '@/components/ui/feedback/alert';
import { Loader2, AlertCircle, CheckCircle } from 'lucide-react';
import { scrapeMonitoredProduct } from '@/lib/api';
import { toast } from 'sonner';

/*
  Página/Componente: AddProduct
  Objetivo: Formulário para adicionar um novo produto ao monitoramento de preços.
  Observações:
    - Validações básicas de entrada (preço alvo numérico e > 0).
    - Chama a API cliente scrapeMonitoredProduct para agendar/registrar o monitoramento.
    - Mostra feedback (erro / sucesso) e redireciona para /products após sucesso.
*/

export default function AddProduct() {
  const { token } = useAuth(); // token de autenticação do usuário (context)
  const [, navigate] = useLocation(); // navegação via wouter
  // Estado do formulário (campos controlados)
  const [formData, setFormData] = useState({
    name_identification: '',
    product_url: '',
    competitor_url: '',
    target_price: '',
  });
  const [isLoading, setIsLoading] = useState(false); // indicador de requisição em progresso
  const [error, setError] = useState<string | null>(null); // mensagem de erro para o usuário
  const [success, setSuccess] = useState(false); // flag para exibir mensagem de sucesso

  // Atualiza o estado do formulário para inputs controlados
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  // Submissão do formulário: valida, chama API e trata estados de UI
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    setIsLoading(true);

    // Verifica se usuário está autenticado
    if (!token) {
      setError('Você precisa estar autenticado');
      setIsLoading(false);
      return;
    }

    try {
      // Converte e valida o preço alvo
      const targetPrice = parseFloat(formData.target_price);

      if (isNaN(targetPrice) || targetPrice <= 0) {
        setError('Preço alvo inválido');
        setIsLoading(false);
        return;
      }

      // Chamada ao cliente API que agenda/registrará o monitoramento
      await scrapeMonitoredProduct(token, {
        name_identification: formData.name_identification,
        product_url: formData.product_url,
        target_price: targetPrice,
      });

      // Sucesso: feedback ao usuário e limpeza do formulário
      setSuccess(true);
      toast.success('Produto adicionado com sucesso!');

      setFormData({
        name_identification: '',
        product_url: '',
        competitor_url: '',
        target_price: '',
      });

      // Redireciona para a lista de produtos após curto delay para o usuário ler a mensagem
      setTimeout(() => {
        navigate('/products');
      }, 2000);
    } catch (err) {
      // Mostra mensagem de erro genérica ou específica quando disponível
      setError(err instanceof Error ? err.message : 'Erro ao adicionar produto');
      toast.error('Erro ao adicionar produto');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Cabeçalho da página */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Adicionar Novo Produto</h1>
        <p className="text-muted-foreground mt-2">Configure um novo produto para monitoramento de preços</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Informações do Produto</CardTitle>
          <CardDescription>Preencha os dados do seu produto e do concorrente</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Alertas de erro */}
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {/* Mensagem de sucesso */}
            {success && (
              <Alert className="bg-green-50 dark:bg-green-950 border-green-200 dark:border-green-800">
                <CheckCircle className="h-4 w-4 text-green-600" />
                <AlertDescription className="text-green-800 dark:text-green-200">
                  Produto adicionado com sucesso! Redirecionando...
                </AlertDescription>
              </Alert>
            )}

            {/* Campo: Nome do produto */}
            <div className="space-y-2">
              <label htmlFor="name_identification" className="text-sm font-medium">
                Nome do Produto
              </label>
              <Input
                id="name_identification"
                name="name_identification"
                placeholder="Ex: Farol Uno Mille Fire"
                value={formData.name_identification}
                onChange={handleChange}
                disabled={isLoading}
                required
              />
            </div>

            {/* Campo: URL do produto principal */}
            <div className="space-y-2">
              <label htmlFor="product_url" className="text-sm font-medium">
                URL do Seu Produto
              </label>
              <Input
                id="product_url"
                name="product_url"
                type="url"
                placeholder="https://produto.mercadolivre.com.br/..."
                value={formData.product_url}
                onChange={handleChange}
                disabled={isLoading}
                required
              />
            </div>

            {/* Campo: Preço alvo */}
            <div className="space-y-2">
              <label htmlFor="target_price" className="text-sm font-medium">
                Preço Alvo (R$)
              </label>
              <Input
                id="target_price"
                name="target_price"
                type="number"
                placeholder="100.00"
                step="0.01"
                value={formData.target_price}
                onChange={handleChange}
                disabled={isLoading}
                required
              />
            </div>

            {/* Campo opcional: URL do concorrente */}
            <div className="space-y-2">
              <label htmlFor="competitor_url" className="text-sm font-medium">
                URL do Concorrente (Opcional)
              </label>
              <Input
                id="competitor_url"
                name="competitor_url"
                type="url"
                placeholder="https://produto.mercadolivre.com.br/..."
                value={formData.competitor_url}
                onChange={handleChange}
                disabled={isLoading}
              />
            </div>

            {/* Botão de submissão com estado de loading */}
            <Button type="submit" className="w-full" disabled={isLoading}>
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isLoading ? 'Adicionando...' : 'Adicionar Produto'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
