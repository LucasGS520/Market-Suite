/**
 * Contexto de toasts reutilizáveis para a aplicação.
 *
 * Oferece uma fila simples de notificações usando Snackbar + Alert do MUI,
 * permitindo que componentes disparem mensagens temporárias padronizadas sem
 * acoplamento direto à hierarquia de layout.
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Snackbar } from '@mui/material';
import type { SnackbarCloseReason } from '@mui/material/Snackbar';
import { useLocation } from 'react-router-dom';

export type ToastSeverity = 'success' | 'info' | 'warning' | 'error';

type ToastOptions = {
  key?: string;
  message: string;
  severity?: ToastSeverity;
  duration?: number;
  persist?: boolean;
  replace?: boolean;
  closeOnClickaway?: boolean;
};

type ToastMessage = ToastOptions & { id: number };

type ToastContextValue = {
  showToast: (toast: ToastOptions) => void;
  dismissToast: (key?: string) => void;
};

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

const DEFAULT_DURATION = 4000;

/**
 * Provider responsável por gerenciar a fila de toasts e renderizar o Snackbar.
 */
export const ToastProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  const location = useLocation();
  const [queue, setQueue] = useState<ToastMessage[]>([]);
  const [open, setOpen] = useState(false);
  const [isExiting, setIsExiting] = useState(false);
  const closingToastIdRef = useRef<number | null>(null);

  const currentToast = queue[0];

  useEffect(() => {
    // Ativa o Snackbar sempre que houver mensagem na fila e ele estiver fechado.
    if (currentToast && !open && !isExiting) {
      setOpen(true);
    }
  }, [currentToast, open, isExiting]);

  useEffect(() => {
    // Limpa a fila de toasts ao navegar para evitar mensagens "presas" na rota anterior
    setQueue([]);
    setOpen(false);
    setIsExiting(false);
    closingToastIdRef.current = null;
  }, [location.key]);

  const showToast = useCallback((toast: ToastOptions) => {
    // Só substitui explicitamente quando `replace: true` for passado.
    const shouldReplace = !!toast.key && toast.replace === true;
    const nextToast: ToastMessage = {
      id: Date.now() + Math.random(),
      key: toast.key,
      message: toast.message,
      severity: toast.severity ?? 'info',
      // Garante duração numérica para evitar comportamento indefinido no autoHide.
      duration: typeof toast.duration === 'number' ? toast.duration : DEFAULT_DURATION,
      persist: toast.persist ?? false,
      replace: shouldReplace,
      closeOnClickaway: toast.closeOnClickaway ?? false,
    };

    setQueue((prev) => {
      // Se houver um toast atualmente visível (open) e não estiver em saída, substituí imediatamente para mostrar feedback instantâneo.
      if (currentToast && open && !isExiting) {
        // Se o chamador explicitou `replace: false`, apenas enfileira atrás do atual.
        if (toast.replace === false) {
          return [...prev, nextToast];
        }

        // Substitui o primeiro item (toast atual) pelo novo, mantendo o restante da fila.
        const [, ...rest] = prev;
        // Garante que o Snackbar perceba a mudança de `key` e apresente o novo toast.
        closingToastIdRef.current = null;
        setIsExiting(false);
        setOpen(true);
        return [nextToast, ...rest];
      }

      // Comportamento padrão: suporte a replace por key quando especificado.
      if (nextToast.replace && nextToast.key) {
        const existingIndex = prev.findIndex((item) => item.key === nextToast.key);
        if (existingIndex !== -1) {
          const updatedQueue = [...prev];
          updatedQueue[existingIndex] = nextToast;
          return updatedQueue;
        }
      }

      return [...prev, nextToast];
    });
  }, [currentToast, open, isExiting]);

  const handleClose = useCallback((_: React.SyntheticEvent | Event | undefined, reason?: SnackbarCloseReason) => {
    // Permite fechamento por clique fora apenas quando explicitamente configurado
    if (reason === 'clickaway' && !currentToast?.closeOnClickaway) return;
    // Marca o toast atual como "fechando" e dispara a transição.
    // Não removemos imediatamente da fila: aguardar o `onExited` garante que a transição visual termine e não bloqueie toasts subsequentes.
    closingToastIdRef.current = currentToast?.id ?? null;
    setIsExiting(true);
    setOpen(false);
  }, [currentToast]);

  const dismissToast = useCallback(
    (key?: string) => {
      if (!key) {
        if (currentToast) {
          // Marca o toast atual para fechamento e aguarda a transição.
          closingToastIdRef.current = currentToast.id;
          setIsExiting(true);
        }
        setOpen(false);
        return;
      }

      // Remove mensagens específicas mantendo o comportamento de fila
      setQueue((prev) => prev.filter((toast) => toast.key !== key));

      // Não remove imediatamente, para não interromper a transição.
      if (currentToast?.key === key) {
        closingToastIdRef.current = currentToast.id;
        setIsExiting(true);
        setOpen(false);
      }
    },
    [currentToast]
  );

  const handleExited = useCallback(() => {
    // Remove o toast marcado e permita que o próximo da fila seja exibido pelo useEffect que observa `currentToast`.
    const closingId = closingToastIdRef.current;
    closingToastIdRef.current = null;
    if (closingId) {
      setQueue((prev) => prev.filter((t) => t.id !== closingId));
    }
    setIsExiting(false);
  }, []);

  const contextValue = useMemo(() => ({ showToast, dismissToast }), [showToast, dismissToast]);

  return (
    <ToastContext.Provider value={contextValue}>
      {children}
      <Snackbar
        key={currentToast?.id}
        open={open}
        autoHideDuration={currentToast?.persist ? null : currentToast?.duration ?? DEFAULT_DURATION}
        onClose={handleClose}
        TransitionProps={{ onExited: handleExited }}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        {currentToast ? (
          <Alert
            severity={currentToast.severity}
            elevation={3}
            onClose={() => handleClose(undefined)}
            sx={{ width: '100%' }}
          >
            {currentToast.message}
          </Alert>
        ) : (
          <></>
        )}
      </Snackbar>
    </ToastContext.Provider>
  );
};

/**
 * Hook auxiliar para consumir o contexto de toasts.
 */
export const useToastContext = (): ToastContextValue => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToastContext deve ser usado dentro de um ToastProvider');
  }
  return context;
};

export default ToastContext;
