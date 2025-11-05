import { useRef } from "react";

type noop = (...args: any[]) => any;

/**
 * usePersistFn pode substituir useCallback para reduzir a carga cognitiva.
 *
 * - Retorna uma função com referência estável (persistente) entre renders.
 * - A implementação garante que a referência retornada nunca muda, mas sempre invoque a versão mais recente de `fn`.
 *
 * Uso: útil quando você precisa passar uma função estável (ex.: dependência de efeitos ou props) sem recriar closures.
 */
export function usePersistFn<T extends noop>(fn: T) {
  // Guarda a referência atual da função. 
  // Atualizado a cada render para que a implementação persistente invoque sempre a versão mais recente.
  const fnRef = useRef<T>(fn);
  fnRef.current = fn;

  // Referência para a função "persistente" que será retornada.
  // Inicializa com null para controle explícito de criação única.
  const persistFn = useRef<T | null>(null);

  // Cria a função persistente apenas uma vez. 
  // Essa função delega a chamada para `fnRef.current`, preservando o this e os argumentos.
  if (!persistFn.current) {
    persistFn.current = function (this: unknown, ...args) {
      return fnRef.current!.apply(this, args);
    } as T;
  }

  // Garantimos não retornar null (o valor foi criado acima, se necessário).
  return persistFn.current as T;
}
