/**
 * """ Página principal com listagem de monitorados e formulário de criação """
 */
import { useEffect, useState } from 'react'

import { apiClient } from '../lib/api'
import { MonitoredProduct } from '../../types/generated-api'
import CreateMonitoredForm from './forms/CreateMonitoredForm'
import MonitoredTable from '../../components/MonitoredTable'

const MonitoredListPage = () => {
  const [items, setItems] = useState<MonitoredProduct[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const fetchMonitored = async () => {
    try {
      setIsLoading(true)
      setErrorMessage(null)
      const response = await apiClient.get<MonitoredProduct[]>('/monitored')
      setItems(response.data)
    } catch (error) {
      setErrorMessage('Não foi possível carregar os monitorados no momento.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    //Comentário: carregamento inicial ao entrar na página; dependências vazias
    fetchMonitored()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-2xl font-semibold text-slate-900">Produtos monitorados</h1>
        <p className="text-sm text-slate-600">
          Acompanhe seus monitoramentos e adicione novos produtos para rastrear preços.
        </p>
      </section>
      <CreateMonitoredForm onCreated={fetchMonitored} />
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">Lista atual</h2>
          <button
            type="button"
            onClick={fetchMonitored}
            className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
          >
            Atualizar
          </button>
        </div>
        {isLoading ? (
          <p className="text-sm text-slate-600">Carregando monitorados...</p>
        ) : errorMessage ? (
          <p className="text-sm text-red-600">{errorMessage}</p>
        ) : (
          <MonitoredTable items={items} />
        )}
      </section>
    </div>
  )
}

export default MonitoredListPage
