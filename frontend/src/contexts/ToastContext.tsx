/**
 * Contexto de toasts reutilizáveis para a aplicação.
 *
 * Oferece uma fila simples de notificações usando Snackbar + Alert do MUI,
 * permitindo que componentes disparem mensagens temporárias padronizadas sem
 * acoplamento direto à hierarquia de layout.
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Alert, Snackbar } from '@mui/material';

export type ToastSeverity = 'success' | 'info' | 'warning' | 'error';

type ToastOptions = {
  message: string;
  severity?: ToastSeverity;
  duration?: number;
};

type ToastMessage = ToastOptions & { id: number };

type ToastContextValue = {
  showToast: (toast: ToastOptions) => void;
};

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

const DEFAULT_DURATION = 4000;

/**
 * Provider responsável por gerenciar a fila de toasts e renderizar o Snackbar.
 */
export const ToastProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  const [queue, setQueue] = useState<ToastMessage[]>([]);
  const [open, setOpen] = useState(false);

  const currentToast = queue[0];

  useEffect(() => {
    // Ativa o Snackbar sempre que houver mensagem na fila e ele estiver fechado.
    if (currentToast && !open) {
      setOpen(true);
    }
  }, [currentToast, open]);

  const showToast = useCallback((toast: ToastOptions) => {
    setQueue((prev) => [
      ...prev,
      {
        id: Date.now() + Math.random(),
        severity: toast.severity ?? 'info',
        duration: toast.duration ?? DEFAULT_DURATION,
        message: toast.message,
      },
    ]);
  }, []);

  const handleClose = useCallback((_: unknown, reason?: string) => {
    // Ignora fechamento por clique fora para evitar descartes acidentais.
    if (reason === 'clickaway') return;
    setOpen(false);
  }, []);

  const handleExited = useCallback(() => {
    // Remove o toast exibido e avança na fila.
    setQueue((prev) => prev.slice(1));
  }, []);

  const contextValue = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={contextValue}>
      {children}
      <Snackbar
        key={currentToast?.id}
        open={open}
        autoHideDuration={currentToast?.duration ?? DEFAULT_DURATION}
        onClose={handleClose}
        TransitionProps={{ onExited: handleExited }}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        {currentToast ? (
          <Alert severity={currentToast.severity} elevation={3} onClose={handleClose} sx={{ width: '100%' }}>
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