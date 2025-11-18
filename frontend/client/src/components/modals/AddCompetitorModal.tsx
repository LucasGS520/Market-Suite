import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/overlay/dialog';
import { Input } from '@/components/ui/inputs/input';
import { Label } from '@/components/ui/inputs/label';
import { Button } from '@/components/ui/button/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/feedback/alert';
import { AlertCircle, Info } from 'lucide-react';
import { toast } from 'sonner';
import { sanitizeExternalUrl } from '@/lib/utils';
import { scrapeCompetitor, type MonitoredProduct } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';

/**
 * Limite padrão de concorrentes permitido por monitorado quando não definido via env.
 */
const DEFAULT_COMPETITOR_LIMIT = 10;

/**
 * Determina o limite máximo de concorrentes considerando variável de ambiente opcional.
 */
const resolveCompetitorLimit = (): number => {
  const raw = import.meta.env.VITE_COMPETITORS_LIMIT;
  const parsed = raw ? Number(raw) : Number.NaN;

  if (Number.isFinite(parsed) && parsed > 0) {
    return parsed;
  }

  return DEFAULT_COMPETITOR_LIMIT;
};

/**
 * Valor máximo de concorrentes permitido para cada produto monitorado.
 */
const COMPETITOR_LIMIT = resolveCompetitorLimit();

/**
 * Propriedades aceitas pelo modal de adição de concorrente.
 */
export interface AddCompetitorModalProps {
  product: MonitoredProduct;
  isOpen: boolean;
  onClose: () => void;
  onScheduled?: (options: { keepOpen: boolean; product: MonitoredProduct }) => void;
}

/**
 * Normaliza URLs removendo hash, querystring e domínios com `www.` para deduplicação.
 */
const canonicalizeCompetitorUrl = (rawUrl: string): string => {
  const trimmed = rawUrl.trim();
  if (!trimmed) {
    throw new Error('Informe uma URL válida do concorrente.');
  }

  const sanitized = sanitizeExternalUrl(trimmed);
  if (!sanitized) {
    throw new Error('Utilize links com protocolo http ou https.');
  }

  const parsed = new URL(sanitized);
  parsed.hash = '';
  parsed.search = '';
  parsed.username = '';
  parsed.password = '';

  // Remove prefixo www. e normaliza porta padrão para alinhar com o backend.
  parsed.hostname = parsed.hostname.replace(/^www\./i, '').toLowerCase();
  if ((parsed.protocol === 'https:' && parsed.port === '443') || (parsed.protocol === 'http:' && parsed.port === '80')) {
    parsed.port = '';
  }

  const normalizedPath = parsed.pathname.replace(/\/+/, '/');
  const trimmedPath = normalizedPath !== '/' ? normalizedPath.replace(/\/+$/, '') : normalizedPath;
  parsed.pathname = trimmedPath || '/';

  return parsed.toString();
};

/**
 * Modal responsável por cadastrar concorrentes em produtos monitorados.
 *
 * - Valida a URL informada pelo usuário antes de acionar o backend.
 * - Bloqueia submissões duplicadas durante a mesma sessão do modal.
 * - Exibe feedback imediato ao atingir o limite configurado de concorrentes.
 */
const AddCompetitorModal: React.FC<AddCompetitorModalProps> = ({ product, isOpen, onClose, onScheduled }) => {
  const { token } = useAuth();
  const [urlValue, setUrlValue] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [recentCanonicalUrls, setRecentCanonicalUrls] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const competitorsCount = product.competitors_count ?? 0;
  const reachedLimit = competitorsCount >= COMPETITOR_LIMIT;
  const remainingSlots = Math.max(COMPETITOR_LIMIT - competitorsCount, 0);

  /**
   * Mensagem contextual sobre o limite para ajudar o usuário a planejar inclusões.
   */
  const limitMessage = useMemo(() => {
    if (reachedLimit) {
      return 'Limite de concorrentes atingido para este produto.';
    }

    if (remainingSlots === 1) {
      return 'Você pode adicionar mais 1 concorrente neste monitoramento.';
    }

    return `Você pode adicionar mais ${remainingSlots} concorrentes.`;
  }, [reachedLimit, remainingSlots]);

  useEffect(() => {
    if (!isOpen) {
      setUrlValue('');
      setFormError(null);
      setRecentCanonicalUrls([]);
      return;
    }

    // Foca o input quando o modal abre para agilizar a interação.
    const focusTimeout = setTimeout(() => {
      inputRef.current?.focus();
    }, 50);

    return () => clearTimeout(focusTimeout);
  }, [isOpen, product.id]);

  /**
   * Fecha o modal ao receber alteração externa do estado aberto/fechado.
   */
  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (!open) {
        onClose();
      }
    },
    [onClose],
  );

  /**
   * Agenda o scraping do concorrente realizando validações prévias.
   */
  const scheduleCompetitor = useCallback(
    async (keepOpen: boolean) => {
      if (!token) {
        const message = 'Sessão expirada. Faça login novamente para adicionar concorrentes.';
        setFormError(message);
        toast.error(message);
        return;
      }

      if (reachedLimit) {
        const message = 'Você atingiu o limite configurado de concorrentes para este produto.';
        setFormError(message);
        toast.error(message);
        return;
      }

      let canonicalUrl: string;
      try {
        canonicalUrl = canonicalizeCompetitorUrl(urlValue);
      } catch (error) {
        const message = error instanceof Error ? error.message : 'URL inválida. Revise o endereço informado.';
        setFormError(message);
        return;
      }

      if (recentCanonicalUrls.includes(canonicalUrl)) {
        setFormError('Este concorrente já foi adicionado recentemente. Utilize outro link.');
        return;
      }

      if (product.product_url) {
        try {
          const monitoredCanonical = canonicalizeCompetitorUrl(product.product_url);
          if (monitoredCanonical === canonicalUrl) {
            setFormError('Informe um concorrente diferente do produto monitorado.');
            return;
          }
        } catch (error) {
          // Ignoramos falhas na normalização do monitorado pois não impedem a inclusão.
        }
      }

      setIsSubmitting(true);
      setFormError(null);

      try {
        await scrapeCompetitor(
          token,
          {
            monitored_product_id: product.id,
            product_url: canonicalUrl,
          },
        );

        setRecentCanonicalUrls((previous) => [...previous, canonicalUrl]);
        toast.success('Concorrente enviado para coleta.');
        onScheduled?.({ keepOpen, product });

        if (keepOpen) {
          setUrlValue('');
          inputRef.current?.focus();
        } else {
          onClose();
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Falha ao adicionar concorrente. Tente novamente.';
        setFormError(message);
        toast.error(message);
      } finally {
        setIsSubmitting(false);
      }
    },
    [token, reachedLimit, urlValue, recentCanonicalUrls, product.id, product.product_url, onScheduled, onClose],
  );

  /**
   * Submissão padrão do formulário salva e fecha o modal.
   */
  const handleSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      await scheduleCompetitor(false);
    },
    [scheduleCompetitor],
  );

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Adicionar concorrente</DialogTitle>
          <DialogDescription>
            Cole a URL do concorrente que deseja monitorar. Validaremos e agendaremos a coleta automaticamente.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="competitor-url">URL do concorrente</Label>
            <Input
              id="competitor-url"
              ref={inputRef}
              placeholder="https://loja.com/produto"
              value={urlValue}
              onChange={(event) => setUrlValue(event.target.value)}
              autoComplete="off"
              required
              disabled={isSubmitting || reachedLimit}
              aria-invalid={Boolean(formError)}
            />
            <p className="text-xs text-muted-foreground">{limitMessage}</p>
          </div>

          {formError && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Não foi possível adicionar o concorrente</AlertTitle>
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          )}

          {recentCanonicalUrls.length > 0 && !reachedLimit && (
            <Alert>
              <Info className="h-4 w-4" />
              <AlertTitle>Concorrentes já enviados nesta sessão</AlertTitle>
              <AlertDescription className="text-xs">
                {recentCanonicalUrls.map((item) => (
                  <p key={item} className="break-all">
                    {item}
                  </p>
                ))}
              </AlertDescription>
            </Alert>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={isSubmitting}>
              Cancelar
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => scheduleCompetitor(true)}
              disabled={isSubmitting || reachedLimit}
            >
              Salvar e adicionar outro
            </Button>
            <Button type="submit" disabled={isSubmitting || reachedLimit}>
              {isSubmitting ? 'Agendando...' : 'Salvar concorrente'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default AddCompetitorModal;
