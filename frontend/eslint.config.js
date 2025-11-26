/**
 * Configuração do ESLint (formato moderno com defineConfig).
 * - Mantém a configuração atual: regras JS recomendadas, integração TypeScript, hooks do React e suporte a refresh do Vite.
 *
 * Notas operacionais:
 * - Este arquivo é carregado pelo ESLint na raiz do frontend.
 * - Ajustes em regras/extends devem ser documentados e sincronizados com README do frontend.
 */

import js from '@eslint/js' // Configurações recomendadas para JavaScript
import globals from 'globals' // Conjunto de variáveis globais (ex.: browser, node)
import reactHooks from 'eslint-plugin-react-hooks' // Regras para Hooks do React
import reactRefresh from 'eslint-plugin-react-refresh' // Integração com Vite React Refresh
import tseslint from 'typescript-eslint' // Integração com TypeScript (preserva import existente)
import { defineConfig, globalIgnores } from 'eslint/config' // Helpers do ESLint moderno

export default defineConfig([
  // Ignora a pasta build/output (ex.: dist) globalmente
  globalIgnores(['dist']),

  {
    // Aplica esta configuração a arquivos TypeScript/TSX
    files: ['**/*.{ts,tsx}'],

    // Extensões/presets aplicados — manter ordem para herança de regras
    extends: [
      js.configs.recommended, // Regras recomendadas para JS
      tseslint.configs.recommended, // Regras recomendadas para TS (preserva import atual)
      reactHooks.configs.flat.recommended, // Regras específicas para Hooks do React (evita bugs comuns)
      reactRefresh.configs.vite, // Regras relacionadas ao Vite + React Refresh
    ],

    languageOptions: {
      // Suporte a sintaxe moderna do ECMAScript
      ecmaVersion: 2020,

      // Define o ambiente global como browser (window, document, etc.)
      globals: globals.browser,
    },
  },
])
