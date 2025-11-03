/**
 * """ Layout geral da aplicação após autenticação; oferece navegação e contexto visual """
 */
import { PropsWithChildren } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'

import { useAuth } from '../features/auth/AuthContext'

export function AppLayout({ children }: PropsWithChildren) {
  const { logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    //Comentário: a navegação ocorre após limpar o token para evitar requisições pendentes autenticadas
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <NavLink to="/" className="text-xl font-semibold text-slate-900">
            MarketSuite
          </NavLink>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-500"
          >
            Sair
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
    </div>
  )
}
