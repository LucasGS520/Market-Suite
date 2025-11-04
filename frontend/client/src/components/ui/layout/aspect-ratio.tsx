// AspectRatio
// Wrapper simples sobre `@radix-ui/react-aspect-ratio`.
// Mantém proporção do conteúdo (útil para vídeos, imagens ou cartões).
import * as AspectRatioPrimitive from "@radix-ui/react-aspect-ratio";

/**
 * AspectRatio
 * - Recebe as props do Radix `AspectRatio.Root` e aplica o data-slot para
 *   consistência do projeto.
 */
function AspectRatio({
  ...props
}: React.ComponentProps<typeof AspectRatioPrimitive.Root>) {
  return <AspectRatioPrimitive.Root data-slot="aspect-ratio" {...props} />;
}

export { AspectRatio };
