import * as React from "react";

/**
 * Largura máxima (em pixels) considerada como "mobile".
 * Dispositivos com largura estritamente menor que este valor são considerados mobile.
 */
const MOBILE_BREAKPOINT = 768;

/**
 * Hook: useIsMobile
 *
 * Retorna um boolean indicando se o viewport atual deve ser tratado como "mobile".
 *
 * Notas:
 * - Usa window.matchMedia para escutar mudanças de largura e atualizar o estado.
 * - Em ambientes sem `window` (ex.: SSR) retorna false por padrão.
 */
export function useIsMobile(): boolean {
  // Estado que representa se o dispositivo é mobile ou não.
  // Inicializa de forma segura para ambientes sem `window`.
  const [isMobile, setIsMobile] = React.useState<boolean>(
    typeof window !== "undefined" ? window.innerWidth < MOBILE_BREAKPOINT : false
  );

  React.useEffect(() => {
    // Proteção para evitar executar em ambiente sem window (SSR).
    if (typeof window === "undefined" || typeof window.matchMedia === "undefined") {
      return;
    }

    // MediaQueryList para escutar mudanças de largura do viewport.
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`);

    // Função chamada sempre que a media query muda.
    const onChange = () => {
      // Atualiza o estado com base na largura atual da janela.
      setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);
    };

    // Registra o listener da media query.
    mql.addEventListener("change", onChange);

    // Define estado inicial com base na largura atual (garante coerência ao montar).
    setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);

    // Cleanup: remove o listener quando o componente que usa o hook desmonta.
    return () => {
      mql.removeEventListener("change", onChange);
    };
  }, []);

  // Retorna sempre um boolean (sem undefined).
  return !!isMobile;
}
