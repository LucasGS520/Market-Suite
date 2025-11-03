/**
 * """ Gerencia autenticação com armazenamento seguro do token e utilitários de sessão """
 */
import { createContext, PropsWithChildren, useContext, useEffect, useMemo, useState } from 'react'

import { AuthToken } from '../../types/generated-api'
import { apiClient, setAuthToken } from '../lib/api'

type AuthContextValue = {
  token: string | null
  isAuthenticated: boolean
  login: (credentials: { username: string; password: string }) => Promise<void>
  logout: () => void
}

const STORAGE_KEY = 'marketsuite.token'

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: PropsWithChildren) {
  const [token, setToken] = useState<string | null>(() => {
    const storedToken = window.localStorage.getItem(STORAGE_KEY)
    if (storedToken) {
      setAuthToken(storedToken)
    }
    return storedToken
  })

  useEffect(() => {
    //Comentário: sincroniza o cabeçalho Authorization com a mutação do token para evitar estado inconsistente
    setAuthToken(token)
    if (token) {
      window.localStorage.setItem(STORAGE_KEY, token)
    } else {
      window.localStorage.removeItem(STORAGE_KEY)
    }
  }, [token])

  const login = async ({ username, password }: { username: string; password: string }) => {
    const body = new URLSearchParams()
    body.append('username', username)
    body.append('password', password)

    const response = await apiClient.post<AuthToken>('/auth', body, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    setToken(response.data.access_token)
  }

  const logout = () => {
    setToken(null)
  }

  const value = useMemo(
    () => ({
      token,
      isAuthenticated: Boolean(token),
      login,
      logout,
    }),
    [token],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth deve ser utilizado dentro de AuthProvider')
  }
  return context
}
