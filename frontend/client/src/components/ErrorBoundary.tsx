// Componente React para capturar erros em componentes filhos e exibir uma UI de fallback.

import { cn } from "@/lib/utils"; // utilitário de concatenação de classes CSS
import { AlertTriangle, RotateCcw } from "lucide-react"; // ícones usados na UI de fallback
import { Component, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/*
  ErrorBoundary:
  - Componente de classe que implementa a API de Error Boundaries do React.
  - Quando um erro ocorre em qualquer componente filho, ele atualiza o estado
    e exibe uma interface amigável com stacktrace e opção de recarregar a página.
*/
class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    // Estado inicial: sem erro
    this.state = { hasError: false, error: null };
  }

  // Atualiza o estado quando um erro é capturado em algum filho.
  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    // Se ocorreu um erro, renderiza a UI de fallback
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center min-h-screen p-8 bg-background">
          <div className="flex flex-col items-center w-full max-w-2xl p-8">
            {/* Ícone de aviso visual */}
            <AlertTriangle
              size={48}
              className="text-destructive mb-6 flex-shrink-0"
            />

            {/* Título simples informando que ocorreu um erro inesperado */}
            <h2 className="text-xl mb-4">Ocorreu um erro inesperado.</h2>

            {/* Exibe o stack trace do erro (se disponível) em um bloco rolável */}
            <div
              role="alert"
              aria-live="polite"
              className="p-4 w-full rounded bg-muted overflow-auto mb-6"
            >
              <pre className="text-sm text-muted-foreground whitespace-break-spaces">
                {this.state.error?.stack}
              </pre>
            </div>

            {/* Botão para recarregar a página e tentar recuperar do erro */}
            <button
              onClick={() => window.location.reload()}
              className={cn(
                "flex items-center gap-2 px-4 py-2 rounded-lg",
                "bg-primary text-primary-foreground",
                "hover:opacity-90 cursor-pointer"
              )}
            >
              <RotateCcw size={16} />
              Recarregar página
            </button>
          </div>
        </div>
      );
    }

    // Se não houve erro, renderiza normalmente as crianças (children)
    return this.props.children;
  }
}

export default ErrorBoundary;
