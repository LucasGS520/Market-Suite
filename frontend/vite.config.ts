/**
 * Configuração do Vite para a aplicação frontend (React + Vite).
 *
 * Este arquivo define as opções principais do dev server usadas 
 * durante desenvolvimento local (porta, host e proxy para a API backend).
 */

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],

  // Configurações do servidor de desenvolvimento
  server: {
    port: 5173, // Porta padrão do Vite para dev server

    // Host true permite que o servidor seja acessado por interfaces externas
    // (0.0.0.0), útil para testes em dispositivos na mesma rede ou em contêineres.
    // Em produção, a app deve ser empacotada e servida por um servidor apropriado.
    host: true,

    // Proxy para encaminhar chamadas de API durante desenvolvimento.
    // Isso evita CORS no ambiente dev e espelha o comportamento do frontend em produção, que consome a API pública do backend.
    proxy: {
      '/api': {
        target: 'http://localhost:8000', // Endereço do backend de desenvolvimento (FastAPI rodando localmente).
        // changeOrigin ajusta o header Host da requisição para o target, útil quando o backend espera um Host específico.
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''), // Reescreve o path removendo o prefixo /api antes de encaminhar.
      },
    },
  },
})