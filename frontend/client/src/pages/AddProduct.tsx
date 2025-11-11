import React, { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useLocation } from 'wouter';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/data-display/card';
import { Button } from '@/components/ui/button/button';
import { Input } from '@/components/ui/inputs/input';
import { Alert, AlertDescription } from '@/components/ui/feedback/alert';
import { Loader2, AlertCircle } from 'lucide-react';
import { scrapeMonitoredProduct } from '@/lib/api';
import { toast } from 'sonner';

/*
  Página/Componente: AddProduct
  Objetivo: Formulário para adicionar um novo produto ao monitoramento de preços.
  Observações:
    - O fluxo envia apenas nome e URL, o backend agenda scraping assíncrono.
    - Mostra feedback imediato via toast e redireciona para /products.
*/

export default function AddProduct() {
  const { token } = useAuth(); // token de autenticação do usuário (context)
  const [, navigate] = useLocation(); // navegação via wouter
  // Estado do formulário (campos controlados)
  const [formData, setFormData] = useState({
    name_identification: '',
    product_url: '',
  });
  const [isLoading, setIsLoading] = useState(false); // indicador de requisição em progresso
  const [error, setError] = useState<string | null>(null); // mensagem de erro para o usuário

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
    setIsLoading(true);

    // Verifica se usuário está autenticado
    if (!token) {
      setError('Você precisa estar autenticado');
      setIsLoading(false);
      return;
    }

    try {
      // Chamada ao cliente API que agenda/registrará o monitoramento
      // Normalizamos o nome para enviar ``null`` quando vazio
      const normalizedName = formData.name_identification.trim();
      const response = await scrapeMonitoredProduct(token, {
        name_identification: normalizedName ? normalizedName : null,
        product_url: formData.product_url,
      });

      const normalizedMessage = response.message ?? 'Scraping agendado com sucesso';
      const isDuplicate = normalizedMessage.toLowerCase().includes('já está sendo monitorado');

      if (isDuplicate) {
        toast.info(normalizedMessage);
      } else {
        toast.success(normalizedMessage);
      }

      setFormData({
        name_identification: '',
        product_url: '',
      });

      navigate('/products');
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
        <h1 className="text-3xl font-bold tracking-tight">Adicionar Novo Produto Monitorado</h1>
        <p className="text-muted-foreground mt-2">
          Cadastre o produto principal para iniciar o acompanhamento e, depois, adicione concorrentes na página dedicada.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Informações do Produto Monitorado</CardTitle>
          <CardDescription>
            Informe os dados do seu produto para acompanhar preços.
            A coleta dos concorrentes pode levar alguns minutos após o cadastro para ser concluída.
          </CardDescription>
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
