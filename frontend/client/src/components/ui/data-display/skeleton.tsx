// Skeleton
// Componente simples para placeholders animados (skeleton loading).
import { cn } from "@/lib/utils";

/**
 * Skeleton
 * - Usado como placeholder visual enquanto conteúdo está carregando.
 * - Mantém `animate-pulse` por padrão; adicione tamanhos via `className`.
 */
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("bg-accent animate-pulse rounded-md", className)}
      {...props}
    />
  );
}

export { Skeleton };
