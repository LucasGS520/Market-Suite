// Utilitário para composição de classes CSS usando clsx + tailwind-merge.
// Mantém a assinatura exportada para uso em componentes React/TSX.

import { clsx, type ClassValue } from "clsx"; // clsx: concatena classes condicionais/arrays/objetos em uma única string
import { twMerge } from "tailwind-merge"; // twMerge: resolve conflitos de classes do Tailwind (ex.: "p-2 p-4" -> "p-4")

/**
 * Combina múltiplos valores de classe e resolve conflitos específicos do Tailwind CSS.
 *
 * - Recebe quaisquer valores aceitos por `clsx` (strings, arrays, objetos condicionais).
 * - Primeiro concatena/normaliza com `clsx`, depois mescla/remova duplicatas conflitantes com `twMerge`.
 *
 * @param inputs - Lista de valores de classe (ClassValue[]).
 * @returns string com as classes finais prontas para uso no atributo `className`.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
