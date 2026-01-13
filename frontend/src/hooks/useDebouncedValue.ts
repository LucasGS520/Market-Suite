/**
 * Hook que retorna um valor com debounce para reduzir chamadas de atualização.
 */

import { useEffect, useState } from 'react';

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
  const [isDebouncing, setIsDebouncing] = useState(false);

  useEffect(() => {
    if (Object.is(value, debouncedValue)) {
      return;
    }
    // Evita chamadas repetidas enquanto o usuário ainda está digitando
    setIsDebouncing(true);
    const timer = window.setTimeout(() => {
      setDebouncedValue(value);
      setIsDebouncing(false);
    }, delay);

    return () => window.clearTimeout(timer);
  }, [value, delay, debouncedValue]);

  return { debouncedValue, isDebouncing };
};

export default useDebouncedValue;
