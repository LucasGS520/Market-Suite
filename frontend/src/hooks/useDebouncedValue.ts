/**
 * Hook que retorna um valor com debounce para reduzir chamadas de atualização.
 */

import { useEffect, useRef, useState } from 'react';

interface DebouncedState<T> {
  debouncedValue: T;
  isDebouncing: boolean;
}

/**
 * useDebouncedValue
 * Aplica debounce a um valor e informa quando a atualização está pendente.
 */
const useDebouncedValue = <T,>(value: T, delay = 800): DebouncedState<T> => {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  const previousValueRef = useRef(value);
  const isDebouncing = !Object.is(value, debouncedValue);

  useEffect(() => {
    if (Object.is(previousValueRef.current, value)) {
      return;
    }
    // Garante debounce apenas quando o valor realmente mudou desde o último ciclo.
    previousValueRef.current = value;
    // Evita chamadas repetidas enquanto o usuário ainda está digitando.
    const timer = window.setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => window.clearTimeout(timer);
  }, [value, delay]);

  return { debouncedValue, isDebouncing };
};

export default useDebouncedValue;
