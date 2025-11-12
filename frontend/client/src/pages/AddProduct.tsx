import React, { useCallback, useRef, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useLocation } from 'wouter';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/data-display/card';
import { Button } from '@/components/ui/button/button';
import { Input } from '@/components/ui/inputs/input';
import { Alert, AlertDescription } from '@/components/ui/feedback/alert';
import { Badge } from '@/components/ui/data-display/badge';
import { Loader2, AlertCircle, Clock, ExternalLink } from 'lucide-react';
import { scrapeMonitoredProduct } from '@/lib/api';
import { toast } from 'sonner';
import { sanitizeExternalUrl } from '@/lib/utils';

/**
 * Página responsável por cadastrar um novo produto monitorado e orientar o usuário sobre os próximos passos.
 * 
 * - Agenda o scraping inicial via POST `/monitored/scrape`.
 * - Mantém o usuário na tela oferecendo atalhos para listar produtos ou cadastrar outro item.
 * - Destaca o último produto agendado para reforçar o estado "Agendado" imediatamente.
 */
type ScheduledProductSummary = {
  nome: string | null;
  url: string;
  mensagem: string;
  agendadoEm: Date;
};

const DUPLICATE_MESSAGE_SNIPPET = 'já está sendo monitorado';
const DEFAULT_POST_SUBMIT_MESSAGE = 'Produto agendado. Escolha uma ação para continuar.';

export default function AddProduct() {
  const { token } = useAuth(); // token de autenticação do usuário (context)
  const [, navigate] = useLocation(); // navegação via wouter
  const nameInputRef = useRef<HTMLInputElement | null>(null); // referência para focar no campo após submissão
  // Estado do formulário (campos controlados)
  const [formData, setFormData] = useState({
    name_identification: '',
    product_url: '',
  });
  const [isLoading, setIsLoading] = useState(false); // indicador de requisição em progresso
  const [error, setError] = useState<string | null>(null); // mensagem de erro para o usuário
  const [showPostSubmitActions, setShowPostSubmitActions] = useState(false); // controla exibição dos botões pós-submissão
  const [scheduledProduct, setScheduledProduct] = useState<ScheduledProductSummary | null>(null); // resumo do último agendamento
  const [postSubmitMessage, setPostSubmitMessage] = useState(DEFAULT_POST_SUBMIT_MESSAGE); // mensagem exibida junto das ações pós-submissão
  const safeScheduledProductUrl = scheduledProduct ? sanitizeExternalUrl(scheduledProduct.url) : null; // URL validada para abrir anúncio

  /**
   * Identifica mensagens vindas da API que sinalizam duplicidade de monitoramento.
   */
  const isDuplicateMessage = useCallback(
    (message: string | null | undefined) => {
      return message?.toLowerCase().includes(DUPLICATE_MESSAGE_SNIPPET) ?? false;
    },
    []
  );

  /**
   * Exibe o feedback positivo/informativo quando o produto já estava monitorado previamente.
   */
  const handleDuplicateFeedback = useCallback(
    (message: string) => {
      // Mantém o usuário informado sem sinalizar erro, pois o produto já está monitorado pelo sistema.
      toast.info(message);
      setError(null);
      setPostSubmitMessage(message);
      setShowPostSubmitActions(true);
      setTimeout(() => {
        nameInputRef.current?.focus();
      }, 0);
    },
    [nameInputRef]
  );

  // Atualiza o estado do formulário para inputs controlados
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setShowPostSubmitActions(false);
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
      const trimmedUrl = formData.product_url.trim();

      if (!trimmedUrl) {
        const validationMessage = 'Informe uma URL válida para o produto.';
        setError(validationMessage);
        toast.error(validationMessage);
        setIsLoading(false);
        return;
      }
      const response = await scrapeMonitoredProduct(token, {
        name_identification: normalizedName ? normalizedName : null,
        product_url: trimmedUrl,
      });

      const normalizedMessage = response.message ?? 'Scraping agendado com sucesso';

      if (isDuplicateMessage(normalizedMessage)) {
        handleDuplicateFeedback(normalizedMessage);
      } else {
        toast.success(normalizedMessage);
        setScheduledProduct({
          nome: normalizedName ? normalizedName : null,
          url: trimmedUrl,
          mensagem: normalizedMessage,
          agendadoEm: new Date(),
        });
        setPostSubmitMessage(normalizedMessage);
        setShowPostSubmitActions(true);
        setTimeout(() => {
          nameInputRef.current?.focus();
        }, 0);
      }

      setFormData({
        name_identification: '',
        product_url: '',
      });
    } catch (err) {
      // Mostra mensagem de erro genérica ou específica quando disponível
      const message = err instanceof Error ? err.message : 'Erro ao adicionar produto';
      if (isDuplicateMessage(message)) {
        handleDuplicateFeedback(message);
      } else {
        setError(message);
        setShowPostSubmitActions(false);
        toast.error(message);
      }
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Redireciona para a lista de produtos monitorados mantendo o contexto após submissão.
   */
  const handleViewProducts = () => {
    navigate('/products');
  };

  /**
   * Limpa indicadores de pós-submissão e direciona foco para cadastrar outro produto rapidamente.
   */
  const handleAddAnother = () => {
    setShowPostSubmitActions(false);
    setError(null);
    setPostSubmitMessage(DEFAULT_POST_SUBMIT_MESSAGE);
    nameInputRef.current?.focus();
  };

  /**
   * Abre o anúncio do produto recém-agendado garantindo URL segura.
   */
  const handleOpenScheduledProduct = () => {
    if (!scheduledProduct) {
      return;
    }

    if (!safeScheduledProductUrl) {
      toast.error('Não foi possível abrir o anúncio cadastrado.');
      return;
    }

    window.open(safeScheduledProductUrl, '_blank', 'noopener');
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
                placeholder="Ex: Produto a ser monitorado - Opcional"
                value={formData.name_identification}
                onChange={handleChange}
                disabled={isLoading}
                ref={nameInputRef}
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
        {showPostSubmitActions && (
          <CardFooter className="flex-col gap-3 border-t pt-6 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">{postSubmitMessage}</p>
            <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
              <Button type="button" variant="outline" onClick={handleViewProducts}>
                Ver produtos monitorados
              </Button>
              <Button type="button" onClick={handleAddAnother}>
                Adicionar outro produto
              </Button>
            </div>
          </CardFooter>
        )}
      </Card>

      {scheduledProduct && (
        <Card role="status" aria-live="polite">
          <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle className="text-lg">Último produto agendado</CardTitle>
              <CardDescription>
                Coleta inicial agendada em {scheduledProduct.agendadoEm.toLocaleString('pt-BR')}.
              </CardDescription>
            </div>
            <Badge variant="outline" className="flex items-center gap-1 whitespace-nowrap text-amber-700 dark:text-amber-300">
              <Clock className="h-3.5 w-3.5" /> Agendado
            </Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <p className="text-xs text-muted-foreground">Nome do produto</p>
              <p className="text-base font-semibold">
                {scheduledProduct.nome?.trim() || 'Produto sem identificação informada'}
              </p>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">URL informada</p>
              <p className="break-all text-sm text-muted-foreground">{scheduledProduct.url}</p>
            </div>
            <Button
              type="button"
              variant="outline"
              className="gap-2"
              onClick={handleOpenScheduledProduct}
              disabled={!safeScheduledProductUrl}
            >
              <ExternalLink className="h-4 w-4" /> Abrir anúncio
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
