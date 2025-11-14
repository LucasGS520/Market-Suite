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

/**
 * Sanitiza URLs externas para evitar abertura de links com esquemas inseguros ou inválidos.
 *
 * - Aceita valores nulos/indefinidos sem lançar exceção.
 * - Garante que apenas protocolos http/https sejam mantidos.
 * - Retorna a URL normalizada ou ``null`` quando não for possível validar o link.
 */
export function sanitizeExternalUrl(rawUrl: string | null | undefined): string | null {
  if (!rawUrl) {
    return null;
  }

  const trimmed = rawUrl.trim();
  if (!trimmed || /[\u0000-\u001F\u007F]/.test(trimmed)) {
    return null;
  }

  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null;
    }

    if (!parsed.hostname) {
      return null;
    }

    parsed.username = '';
    parsed.password = '';
    
    return parsed.toString();
  } catch (error) {
    return null;
  }
}
