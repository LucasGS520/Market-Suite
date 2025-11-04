// Collapsible
// Wrappers para componentes Radix Collapsible — comportamentos simples para esconder/mostrar conteúdo.
import * as CollapsiblePrimitive from "@radix-ui/react-collapsible";

/**
 * Collapsible
 * - Root para controlar o estado colapsável.
 */
function Collapsible({
  ...props
}: React.ComponentProps<typeof CollapsiblePrimitive.Root>) {
  return <CollapsiblePrimitive.Root data-slot="collapsible" {...props} />;
}

/**
 * CollapsibleTrigger
 * - Elemento que controla abrir/fechar (trigger).
 */
function CollapsibleTrigger({
  ...props
}: React.ComponentProps<typeof CollapsiblePrimitive.CollapsibleTrigger>) {
  return (
    <CollapsiblePrimitive.CollapsibleTrigger
      data-slot="collapsible-trigger"
      {...props}
    />
  );
}

/**
 * CollapsibleContent
 * - Conteúdo que é revelado quando aberto.
 */
function CollapsibleContent({
  ...props
}: React.ComponentProps<typeof CollapsiblePrimitive.CollapsibleContent>) {
  return (
    <CollapsiblePrimitive.CollapsibleContent
      data-slot="collapsible-content"
      {...props}
    />
  );
}

export { Collapsible, CollapsibleTrigger, CollapsibleContent };
