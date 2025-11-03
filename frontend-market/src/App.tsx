/**
 * Define as rotas principais e aplica a proteção por autenticação
 */
import { Navigate, Outlet, Route, Routes } from 'react-router-dom'

import { useAuth } from './features/auth/AuthContext'
import { AppLayout } from './components/AppLayout'
import LoginPage from './features/auth/LoginPage'
import MonitoredListPage from './features/monitored/MonitoredListPage'
import MonitoredDetailPage from './features/monitored/MonitoredDetailPage'

function ProtectedRoute() {
  const { isAuthenticated } = useAuth()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return (
    <AppLayout>
      <Outlet />
    </AppLayout>
  )
}

function PublicOnlyRoute() {
  const { isAuthenticated } = useAuth()

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}

const App = () => {
  return (
    <Routes>
      <Route element={<PublicOnlyRoute />}>
        <Route path="/login" element={<LoginPage />} />
      </Route>
      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<MonitoredListPage />} />
        <Route path="/monitored/:monitoredId" element={<MonitoredDetailPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
