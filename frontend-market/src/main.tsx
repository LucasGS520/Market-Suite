/**
 * """ Ponto de entrada do frontend; inicializa contexto de autenticação e roteamento """
 */
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import App from './App'
import { AuthProvider } from './features/auth/AuthContext'
import './index.css'

const rootElement = document.getElementById('root')

if (!rootElement) {
  throw new Error('Elemento raiz não encontrado para montar a aplicação')
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
