import { useRef } from "react";
import { usePersistFn } from "./usePersistFn";

/**
 *  Retorno do hook useComposition.
 *  - onCompositionStart / onCompositionEnd: handlers para eventos de composição (IME).
 *  - onKeyDown: handler para keydown que respeita o estado de composição.
 *  - isComposing: função que indica se o input está em estado de composição.
 */
export interface UseCompositionReturn<
  T extends HTMLInputElement | HTMLTextAreaElement,
> {
  onCompositionStart: React.CompositionEventHandler<T>;
  onCompositionEnd: React.CompositionEventHandler<T>;
  onKeyDown: React.KeyboardEventHandler<T>;
  isComposing: () => boolean;
}

/**
 *  Opções para configurar o hook.
 *  Permite passar handlers originais que serão chamados após o comportamento padrão.
 */
export interface UseCompositionOptions<
  T extends HTMLInputElement | HTMLTextAreaElement,
> {
  onKeyDown?: React.KeyboardEventHandler<T>;
  onCompositionStart?: React.CompositionEventHandler<T>;
  onCompositionEnd?: React.CompositionEventHandler<T>;
}

type TimerResponse = ReturnType<typeof setTimeout>;

/**
 *  Hook para gerenciar eventos de composição (IME) em inputs/textarea.
 *
 *  Objetivo:
 *  - Controlar quando estamos em composição para evitar que Enter/Escape sejam tratados prematuramente (ex.: enviar formulário).
 *  - Aplicar workaround para Safari onde compositionend pode ser chamado antes do onKeyDown.
 *
 *  Uso:
 *  const { onCompositionStart, onCompositionEnd, onKeyDown, isComposing } = useComposition();
 *  <input onCompositionStart={onCompositionStart} onCompositionEnd={onCompositionEnd} onKeyDown={onKeyDown} />
 */
export function useComposition<
  T extends HTMLInputElement | HTMLTextAreaElement = HTMLInputElement,
>(options: UseCompositionOptions<T> = {}): UseCompositionReturn<T> {
  const {
    onKeyDown: originalOnKeyDown,
    onCompositionStart: originalOnCompositionStart,
    onCompositionEnd: originalOnCompositionEnd,
  } = options;

  // Flag que indica se estamos em estado de composição (IME) atualmente.
  const c = useRef(false);
  // Dois timers auxiliares usados para o workaround do Safari.
  const timer = useRef<TimerResponse | null>(null);
  const timer2 = useRef<TimerResponse | null>(null);

  /**
   *  Handler para início da composição.
   *  - Limpa timers pendentes (se houver).
   *  - Marca que estamos em composição.
   *  - Chama o handler original (se fornecido).
   */
  const onCompositionStart = usePersistFn((e: React.CompositionEvent<T>) => {
    // Limpa timers pendentes para evitar que a flag seja removida indevidamente.
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    if (timer2.current) {
      clearTimeout(timer2.current);
      timer2.current = null;
    }
    c.current = true;
    originalOnCompositionStart?.(e);
  });

  /**
   *  Handler para fim da composição.
   *  - Usa dois setTimeout encadeados como workaround para Safari,
   *    garantindo que onKeyDown associado ao evento final seja processado
   *    antes de definirmos c.current = false.
   *  - Chama o handler original (se fornecido).
   */
  const onCompositionEnd = usePersistFn((e: React.CompositionEvent<T>) => {
    // Usa duas camadas de setTimeout para lidar com casos em Safari onde
    // compositionend é disparado antes de onKeyDown.
    timer.current = setTimeout(() => {
      timer2.current = setTimeout(() => {
        c.current = false;
      });
    });
    originalOnCompositionEnd?.(e);
  });

  /**
   *  Handler para keydown que respeita o estado de composição.
   *  - Se estiver compondo, impede a propagação de Escape e Enter (exceto Shift+Enter).
   *    Isso evita ações indesejadas (ex.: fechar modais ou submeter formulários).
   *  - Caso contrário, delega para o handler original (se houver).
   */
  const onKeyDown = usePersistFn((e: React.KeyboardEvent<T>) => {
    if (
      c.current &&
      (e.key === "Escape" || (e.key === "Enter" && !e.shiftKey))
    ) {
      // Evita que eventos críticos vazem enquanto o usuário está digitando via IME.
      e.stopPropagation();
      return;
    }
    originalOnKeyDown?.(e);
  });

  /**
   *  Retorna se atualmente estamos em composição.
   *  Útil para lógica condicional no componente consumidor.
   */
  const isComposing = usePersistFn(() => {
    return c.current;
  });

  return {
    onCompositionStart,
    onCompositionEnd,
    onKeyDown,
    isComposing,
  };
}
