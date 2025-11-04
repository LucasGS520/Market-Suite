// Spinner
// Icone animado usado para indicar carregamento.
import { Loader2Icon } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Spinner
 * - Componente que exibe um ícone animado (spin). Usa `aria-label` e `role` para acessibilidade.
 */
function Spinner({ className, ...props }: React.ComponentProps<"svg">) {
  return (
    <Loader2Icon
      role="status"
      aria-label="Loading"
      className={cn("size-4 animate-spin", className)}
      {...props}
    />
  );
}

export { Spinner };
