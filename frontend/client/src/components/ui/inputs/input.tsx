// Input
// Componente de input compartilhado que adiciona suporte a
// composição (IME) e integração com o contexto de composição do `Dialog`
// para evitar submissões acidentais enquanto o usuário está compondo texto.
import { useDialogComposition } from "@/components/ui/overlay/dialog";
import { useComposition } from "@/hooks/useComposition";
import { cn } from "@/lib/utils";
import * as React from "react";

/**
 * Input
 * - Envolve um `<input>` HTML padrão com handlers para eventos de composição (IME).
 * - Encaminha o `ref` recebido para o elemento nativo, permitindo foco controlado externamente.
 * - Bloqueia a tecla Enter enquanto o usuário está em composição (útil para idiomas CJK).
 */
const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  (
    {
      className,
      type,
      onKeyDown,
      onCompositionStart,
      onCompositionEnd,
      ...props
    },
    ref
  ) => {
    // Contexto de composição do Dialog (se presente). Em outros contextos, é no-op.
    const dialogComposition = useDialogComposition();

    // Hook utilitário que fornece handlers de composição (IME) e onKeyDown com suporte a composição.
    const {
      onCompositionStart: handleCompositionStart,
      onCompositionEnd: handleCompositionEnd,
      onKeyDown: handleKeyDown,
    } = useComposition<HTMLInputElement>({
      onKeyDown: (e) => {
        // Detecta se está em composição a partir do evento nativo (IME) ou se o dialog acabou de finalizar composição.
        const isComposing =
          (e.nativeEvent as any).isComposing || dialogComposition.justEndedComposing();

        // Se for Enter durante composição (ou imediatamente após), bloquear para evitar submissões indesejadas.
        if (e.key === "Enter" && isComposing) {
          return;
        }

        // Caso contrário, delega ao onKeyDown provido pelo usuário do componente.
        onKeyDown?.(e);
      },
      onCompositionStart: (e) => {
        // Marca no contexto do Dialog que estamos compondo texto.
        dialogComposition.setComposing(true);
        onCompositionStart?.(e);
      },
      onCompositionEnd: (e) => {
        // Indica que a composição acabou recentemente (ajuda a tratar Enter que confirma input).
        dialogComposition.markCompositionEnd();

        // Adia a limpeza do estado `composing` para contornar ordem de eventos em alguns navegadores (ex: Safari).
        setTimeout(() => {
          dialogComposition.setComposing(false);
        }, 100);

        onCompositionEnd?.(e);
      },
    });

    return (
      <input
        // Ref encaminhado para permitir foco externo/controlado
        ref={ref}
        type={type}
        data-slot="input" // atributo usado por bibliotecas/estilos para localizar o elemento
        className={cn(
          // Classes utilitárias para aparência, foco, estados de erro e responsividade.
          "file:text-foreground placeholder:text-muted-foreground selection:bg-primary selection:text-primary-foreground dark:bg-input/30 border-input h-9 w-full min-w-0 rounded-md border bg-transparent px-3 py-1 text-base shadow-xs transition-[color,box-shadow] outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
          "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
          "aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive",
          className
        )}
        // Handlers para IME/composition e teclado (comportamento já tratado no hook)
        onCompositionStart={handleCompositionStart}
        onCompositionEnd={handleCompositionEnd}
        onKeyDown={handleKeyDown}
        {...props}
      />
    );
  }
);

// Definimos `displayName` para manter identificação consistente em ferramentas de debug.
Input.displayName = "Input";

export { Input };
