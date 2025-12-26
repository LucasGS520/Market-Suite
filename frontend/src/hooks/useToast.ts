/**
 * Hook para exibir toasts em qualquer componente.
 *
 * Encapsula o contexto de toasts e expõe helpers com severidades nomeadas
 * para reduzir duplicação ao mostrar mensagens rápidas de feedback.
 * 
 * Uso recomendado:
 * - showToast({ key, message, severity, duration, persist, replace })
 * - dismissToast(key)
 */
import { useMemo } from 'react';
import { useToastContext } from '../contexts/ToastContext';
import type { ToastSeverity } from '../contexts/ToastContext';

type ShowToastParams = {
  key?: string;
  message: string;
  severity?: ToastSeverity;
  duration?: number;
  persist?: boolean;
  replace?: boolean;
  closeOnClickaway?: boolean;
};

export const useToast = () => {
  const { showToast, dismissToast } = useToastContext();

  const helpers = useMemo(
    () => ({
      showToast: (params: ShowToastParams) => showToast(params),
      dismissToast: (key?: string) => dismissToast(key),
      success: (message: string, duration?: number) => showToast({ message, severity: 'success', duration }),
      info: (message: string, duration?: number) => showToast({ message, severity: 'info', duration }),
      warning: (message: string, duration?: number) => showToast({ message, severity: 'warning', duration }),
      error: (message: string, duration?: number) => showToast({ message, severity: 'error', duration }),
    }),
    [dismissToast, showToast]
  );

  return helpers;
};

export default useToast;
