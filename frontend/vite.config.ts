/**
 * Arquivo de configuração do Vite para o frontend.
 * Contém plugins, aliases de importação, diretórios de ambiente/raiz,
 * configurações de build e do servidor de desenvolvimento.
 */

import { jsxLocPlugin } from "@builder.io/vite-plugin-jsx-loc";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "path";
import { defineConfig } from "vite";
import { vitePluginManusRuntime } from "vite-plugin-manus-runtime";

// Lista de plugins aplicados pelo Vite durante o build/dev
// - react(): suporte a React (JSX/TSX)
// - tailwindcss(): integração com Tailwind via plugin oficial
// - jsxLocPlugin(): adiciona metadados de localização JSX (útil para debugging)
// - vitePluginManusRuntime(): plugin específico do projeto (runtime customizado)
const plugins = [react(), tailwindcss(), jsxLocPlugin(), vitePluginManusRuntime()];

export default defineConfig({
  plugins,

  // Resolução de caminhos e aliases para facilitar imports absolutos
  resolve: {
    alias: {
      // Alias para a pasta do cliente (código fonte do frontend)
      "@": path.resolve(import.meta.dirname, "client", "src"),
      // Alias para diretório compartilhado entre serviços
      "@shared": path.resolve(import.meta.dirname, "shared"),
      // Alias para assets anexados ao projeto
      "@assets": path.resolve(import.meta.dirname, "attached_assets"),
    },
  },

  // Diretório onde estão os arquivos .env usados pelo Vite (variáveis de ambiente)
  envDir: path.resolve(import.meta.dirname),

  // Diretório raiz do projeto frontend (onde o Vite considera o index.html)
  root: path.resolve(import.meta.dirname, "client"),

  // Configurações de build de produção
  build: {
    // Pasta de saída final dos artefatos públicos gerados pelo build
    outDir: path.resolve(import.meta.dirname, "dist/public"),
    // Limpa o diretório de saída antes de gerar novos arquivos
    emptyOutDir: true,
  },

  // Configurações do servidor de desenvolvimento (vite dev server)
  server: {
    // Porta padrão para desenvolvimento
    port: 3000,
    // Se false, falha ao tentar ligar na porta; true permite tentar a próxima porta livre
    strictPort: false, // Encontrará a próxima porta disponível se 3000 estiver em uso
    // Habilita binding do host para acessos externos (útil em containers)
    host: true,
    // Hosts permitidos para requisições durante o desenvolvimento
    allowedHosts: [
      ".manuspre.computer",
      ".manus.computer",
      ".manus-asia.computer",
      ".manuscomputer.ai",
      ".manusvm.computer",
      "localhost",
      "127.0.0.1",
    ],
    // Controle de acesso ao sistema de arquivos pelo dev server do Vite
    fs: {
      // Quando true, o Vite só permitirá acesso a pastas explicitamente dentro do root/permitidas
      strict: true,
      // Padrões negados; aqui evita acesso a arquivos ocultos (ex.: .git, .env locais)
      deny: ["**/.*"],
    },
  },
});
