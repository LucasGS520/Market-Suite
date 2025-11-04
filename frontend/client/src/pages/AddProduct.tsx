import React, { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useLocation } from 'wouter';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, AlertCircle, CheckCircle } from 'lucide-react';
import { scrapeMonitoredProduct } from '@/lib/api';
import { toast } from 'sonner';

export default function AddProduct() {
  const { token } = useAuth();
  const [, navigate] = useLocation();
  const [formData, setFormData] = useState({
    name_identification: '',
    product_url: '',
    competitor_url: '',
    target_price: '',
  });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    setIsLoading(true);

    if (!token) {
      setError('Você precisa estar autenticado');
      setIsLoading(false);
      return;
    }

    try {
      const targetPrice = parseFloat(formData.target_price);

      if (isNaN(targetPrice) || targetPrice <= 0) {
        setError('Preço alvo inválido');
        setIsLoading(false);
        return;
      }

      await scrapeMonitoredProduct(token, {
        name_identification: formData.name_identification,
        product_url: formData.product_url,
        target_price: targetPrice,
      });

      setSuccess(true);
      toast.success('Produto adicionado com sucesso!');

      // Limpando o formulário
      setFormData({
        name_identification: '',
        product_url: '',
        competitor_url: '',
        target_price: '',
      });

      // Redirecionando após 2 segundos
      setTimeout(() => {
        navigate('/products');
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao adicionar produto');
      toast.error('Erro ao adicionar produto');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
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
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {success && (
              <Alert className="bg-green-50 dark:bg-green-950 border-green-200 dark:border-green-800">
                <CheckCircle className="h-4 w-4 text-green-600" />
                <AlertDescription className="text-green-800 dark:text-green-200">
                  Produto adicionado com sucesso! Redirecionando...
                </AlertDescription>
              </Alert>
            )}

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
