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
    const shouldReplace = !!toast.key && toast.replace !== false;
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
  }, []);

  const handleClose = useCallback((_: React.SyntheticEvent | Event | undefined, reason?: SnackbarCloseReason) => {
    // Permite fechamento por clique fora apenas quando explicitamente configurado
    if (reason === 'clickaway' && !currentToast?.closeOnClickaway) return;
    closingToastIdRef.current = currentToast?.id ?? null;
    if (currentToast) {
      // Remove imediatamente o toast atual para evitar dependência exclusiva do onExited.
      setQueue((prev) => prev.filter((toast) => toast.id !== currentToast.id));
    }
    setIsExiting(true);
    setOpen(false);
  }, [currentToast]);

  const dismissToast = useCallback(
    (key?: string) => {
      if (!key) {
        if (currentToast) {
          closingToastIdRef.current = currentToast.id;
          // Remove imediatamente o toast exibido antes de iniciar a transição.
          setQueue((prev) => prev.filter((toast) => toast.id !== currentToast.id));
          setIsExiting(true);
        }
        setOpen(false);
        return;
      }

      // Remove mensagens específicas mantendo o comportamento de fila
      setQueue((prev) => prev.filter((toast) => toast.key !== key));

      if (currentToast?.key === key) {
        closingToastIdRef.current = currentToast.id;
        setIsExiting(true);
        setOpen(false);
      }
    },
    [currentToast]
  );

  const handleExited = useCallback(() => {
    // Marca fim da transição e remove o toast exibido somente se ainda estiver na fila.
    setIsExiting(false);
    const closingId = closingToastIdRef.current;
    closingToastIdRef.current = null;
    if (!closingId) return;
    setQueue((prev) => {
      if (prev[0]?.id === closingId) {
        return prev.slice(1);
      }
      return prev;
    });
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
            onClose={() => handleClose(undefined, 'close')}
            sx={{ width: '100%' }}
          >
            {currentToast.message}
          </Alert>
        ) : null}
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
