/**
 * Hook para exibir toasts em qualquer componente.
 *
 * Encapsula o contexto de toasts e expõe helpers com severidades nomeadas
 * para reduzir duplicação ao mostrar mensagens rápidas de feedback.
 */
import { useMemo } from 'react';
import { useToastContext } from '../contexts/ToastContext';
import type { ToastSeverity } from '../contexts/ToastContext';

type ShowToastParams = {
  message: string;
  severity?: ToastSeverity;
  duration?: number;
};

export const useToast = () => {
  const { showToast } = useToastContext();

  const helpers = useMemo(
    () => ({
      show: (params: ShowToastParams) => showToast(params),
      success: (message: string, duration?: number) => showToast({ message, severity: 'success', duration }),
      info: (message: string, duration?: number) => showToast({ message, severity: 'info', duration }),
      warning: (message: string, duration?: number) => showToast({ message, severity: 'warning', duration }),
      error: (message: string, duration?: number) => showToast({ message, severity: 'error', duration }),
    }),
    [showToast]
  );

  return helpers;
};

export default useToast;