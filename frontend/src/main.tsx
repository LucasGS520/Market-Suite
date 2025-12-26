/**
 * Ponto de entrada da aplicação React (Vite).
 * - Inicializa o root do React usando the new createRoot API (React 18+).
 * - Envolve o componente App com StrictMode para ativar verificações adicionais em desenvolvimento.
 */

import { StrictMode } from 'react' // Ativa verificações adicionas em desenvolvimento (não afeta produção)
import { createRoot } from 'react-dom/client' // Nova API de montagem do React 18+
import './index.css' // Estilos globais da aplicação
import App from './App.tsx' // Componente raiz da aplicação
import { ToastProvider } from './contexts/ToastContext.tsx' // Provedor global de toasts reutilizáveis

// Obtém o elemento root do DOM onde a aplicação será montada.
const rootElement = document.getElementById('root')!

// Cria a raiz React e renderiza o App dentro de StrictMode.
// StrictMode ajuda a identificar práticas inseguras e side-effects inesperados durante o desenvolvimento.
createRoot(rootElement).render(
  <StrictMode>
    <ToastProvider>
      <App />
    </ToastProvider>
  </StrictMode>,
)
