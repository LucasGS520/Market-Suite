/*
 ThemeContext.tsx — Provedor de tema (light / dark) para a aplicação

 Este arquivo expõe:
 - ThemeProvider: componente que aplica e persiste o tema (quando habilitado).
 - useTheme: hook para consumir o tema e a função de alternância.
*/

import React, { createContext, useContext, useEffect, useState } from "react";

type Theme = "light" | "dark";

/**
 * Descreve o shape do contexto de tema.
 * - theme: tema atual ("light" | "dark")
 * - toggleTheme: função opcional para alternar o tema (presente apenas se switchable = true)
 * - switchable: indica se o tema pode ser alternado/persistido
 */
interface ThemeContextType {
  theme: Theme;
  toggleTheme?: () => void;
  switchable: boolean;
}

/* Contexto React padrão; undefined enquanto não houver Provider. */
const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

interface ThemeProviderProps {
  children: React.ReactNode;
  defaultTheme?: Theme;
  switchable?: boolean;
}

/**
 * ThemeProvider
 * - Fornece o tema atual para a árvore de componentes.
 * - Se switchable=true, lê/escreve o tema em localStorage e habilita toggleTheme.
 *
 * Props:
 * - defaultTheme: tema usado quando não há persistência (default: "light")
 * - switchable: controla se o usuário pode trocar o tema e se o valor é persistido (default: false)
 */
export function ThemeProvider({
  children,
  defaultTheme = "light",
  switchable = false,
}: ThemeProviderProps) {
  // Inicializa o estado do tema. Se switchable, tenta recuperar de localStorage.
  const [theme, setTheme] = useState<Theme>(() => {
    if (switchable) {
      const stored = localStorage.getItem("theme");
      return (stored as Theme) || defaultTheme;
    }
    return defaultTheme;
  });

  // Efeito que sincroniza a classe root e, se habilitado, persiste o tema.
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "dark") {
      root.classList.add("dark"); // aplica modo escuro no root (Tailwind/estilos base)
    } else {
      root.classList.remove("dark");
    }

    // Persiste somente quando a troca de tema está habilitada
    if (switchable) {
      localStorage.setItem("theme", theme);
    }
  }, [theme, switchable]);

  // Função de alternância disponível apenas quando switchable === true
  const toggleTheme = switchable
    ? () => {
        setTheme(prev => (prev === "light" ? "dark" : "light"));
      }
    : undefined;

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, switchable }}>
      {children}
    </ThemeContext.Provider>
  );
}

/**
 * useTheme
 * - Hook para acessar o contexto de tema.
 * - Lança erro se usado fora do ThemeProvider, facilitando debug.
 */
export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return context;
}
