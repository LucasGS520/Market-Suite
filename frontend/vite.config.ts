/**
 * Configuracao do Vite para a aplicacao frontend (React + Vite).
 *
 * Este arquivo define as opcoes principais do dev server usadas
 * durante desenvolvimento local (porta e host).
 * A URL da API e lida da familia `frontend/.env.frontend*`, sem depender
 * do padrao automatico `.env*` do Vite.
 */

import fs from 'node:fs'
import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

function parseFrontendEnvFile(filePath: string): Record<string, string> {
  if (!fs.existsSync(filePath)) {
    return {}
  }

  const env: Record<string, string> = {}
  const content = fs.readFileSync(filePath, 'utf8')

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) {
      continue
    }

    const separatorIndex = line.indexOf('=')
    if (separatorIndex <= 0) {
      continue
    }

    const key = line.slice(0, separatorIndex).trim()
    let value = line.slice(separatorIndex + 1).trim()

    if (
      value.length >= 2 &&
      ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'")))
    ) {
      value = value.slice(1, -1)
    }

    env[key] = value
  }

  return env
}

function loadFrontendEnv(mode: string): Record<string, string> {
  const root = process.cwd()
  return {
    ...parseFrontendEnvFile(path.join(root, '.env.frontend')),
    ...parseFrontendEnvFile(path.join(root, `.env.frontend.${mode}`)),
  }
}

export default defineConfig(({ mode }) => {
  const frontendEnv = loadFrontendEnv(mode)
  const defineEnv = Object.fromEntries(
    Object.entries(frontendEnv)
      .filter(([key]) => key.startsWith('VITE_'))
      .map(([key, value]) => [`import.meta.env.${key}`, JSON.stringify(value)]),
  )

  Object.assign(process.env, frontendEnv)

  return {
    plugins: [react()],
    define: defineEnv,

    // Configuracoes do servidor de desenvolvimento
    server: {
      port: 5173,

      // Host true permite acesso por interfaces externas (0.0.0.0),
      // util para testes em conteineres ou dispositivos na mesma rede.
      host: true,
    },
  }
})
