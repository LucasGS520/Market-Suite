// Toaster (Sonner)
// Adapta o `Toaster` da lib `sonner` ao tema do Next (next-themes)
// e mapeia variáveis CSS para manter consistência visual com o design tokens.
import { useTheme } from "next-themes";
import { Toaster as Sonner, type ToasterProps } from "sonner";

/**
 * Toaster
 * - Wrapper que sincroniza o tema do Next (`useTheme`) com o `sonner` Toaster.
 * - Define variáveis CSS para ajustar cores de fundo, texto e borda.
 */
const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme();

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      className="toaster group"
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
        } as React.CSSProperties
      }
      {...props}
    />
  );
};

export { Toaster };
