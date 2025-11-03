/**
 * """ Exibe detalhes de um monitorado, seus concorrentes e resultados recentes """
 */
import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'

import { apiClient } from '../lib/api'
import {
  CompetitorProduct,
  ManualComparisonPayload,
  ManualComparisonResult,
  MonitoredProduct,
  PriceComparison,
} from '../../types/generated-api'
import CreateCompetitorForm from '../competitor/forms/CreateCompetitorForm'

const formatCurrency = (value: string | number | null | undefined) => {
  if (value === null || value === undefined) {
    return '—'
  }
  const numeric = typeof value === 'string' ? Number(value) : value
  if (Number.isNaN(numeric)) {
    return '—'
  }
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(numeric)
}

type ManualComparisonFormData = {
  tolerance?: number
  price_change_threshold?: number
}

const MonitoredDetailPage = () => {
  const { monitoredId } = useParams<{ monitoredId: string }>()
  const [monitored, setMonitored] = useState<MonitoredProduct | null>(null)
  const [competitors, setCompetitors] = useState<CompetitorProduct[]>([])
  const [comparisons, setComparisons] = useState<PriceComparison[]>([])
  const [manualResult, setManualResult] = useState<ManualComparisonResult | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [comparisonError, setComparisonError] = useState<string | null>(null)
  const [isRunningComparison, setIsRunningComparison] = useState(false)

  const { register, handleSubmit, reset } = useForm<ManualComparisonFormData>()

  const monitoredIdSafe = useMemo(() => monitoredId ?? '', [monitoredId])

  const fetchDetail = async (showSpinner = false) => {
    if (!monitoredIdSafe) {
      return
    }
    try {
      if (showSpinner) {
        setIsLoading(true)
      }
      setLoadError(null)
      const [monitoredRes, competitorsRes, comparisonsRes] = await Promise.all([
        apiClient.get<MonitoredProduct>(`/monitored/${monitoredIdSafe}`),
        apiClient.get<CompetitorProduct[]>(`/competitors/${monitoredIdSafe}`),
        apiClient.get<PriceComparison[]>(`/comparisons/${monitoredIdSafe}`),
      ])
      setMonitored(monitoredRes.data)
      setCompetitors(competitorsRes.data)
      setComparisons(comparisonsRes.data)
    } catch (error) {
      setLoadError('Não foi possível carregar os detalhes do monitorado.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    //Comentário: a busca depende do identificador presente na rota
    fetchDetail(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [monitoredIdSafe])

  const onManualComparison = async (formData: ManualComparisonFormData) => {
    if (!monitoredIdSafe) {
      return
    }
    try {
      setComparisonError(null)
      setIsRunningComparison(true)
      const payload: ManualComparisonPayload = {
        tolerance: formData.tolerance,
        price_change_threshold: formData.price_change_threshold,
      }
      const response = await apiClient.post<ManualComparisonResult>(`/comparisons/${monitoredIdSafe}/run`, undefined, {
        params: payload,
      })
      setManualResult(response.data)
      await fetchDetail(false)
      reset()
    } catch (error) {
      setComparisonError('Falha ao executar a comparação manual.')
    } finally {
      setIsRunningComparison(false)
    }
  }

  if (isLoading && !monitored) {
    return <p className="text-sm text-slate-600">Carregando detalhes...</p>
  }

  if (loadError && !monitored) {
    return <p className="text-sm text-red-600">{loadError}</p>
  }

  if (!monitored) {
    return <p className="text-sm text-slate-600">Monitorado não encontrado.</p>
  }

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-semibold text-slate-900">{monitored.name_identification ?? 'Produto monitorado'}</h1>
          <a
            href={monitored.product_url ?? '#'}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-slate-600 hover:text-slate-800"
          >
            {monitored.product_url ?? 'URL indisponível'}
          </a>
          {loadError && (
            <p className="text-sm text-red-600">{loadError}</p>
          )}
          <dl className="grid grid-cols-1 gap-4 pt-2 text-sm md:grid-cols-3">
            <div>
              <dt className="font-medium text-slate-600">Preço atual</dt>
              <dd className="text-slate-900">{formatCurrency(monitored.current_price)}</dd>
            </div>
            <div>
              <dt className="font-medium text-slate-600">Preço alvo</dt>
              <dd className="text-slate-900">{formatCurrency(monitored.target_price)}</dd>
            </div>
            <div>
              <dt className="font-medium text-slate-600">Última verificação</dt>
              <dd className="text-slate-900">
                {monitored.last_checked ? new Date(monitored.last_checked).toLocaleString('pt-BR') : '—'}
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="grid gap-6 md:grid-cols-2">
        <CreateCompetitorForm monitoredId={monitoredIdSafe} onCreated={() => fetchDetail(false)} />
        <form
          onSubmit={handleSubmit(onManualComparison)}
          className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
        >
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Comparação manual</h2>
            <p className="text-sm text-slate-600">
              Ajuste os parâmetros de tolerância para recalcular a comparação imediatamente.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label htmlFor="tolerance" className="mb-1 block text-sm font-medium text-slate-700">
                Tolerância
              </label>
              <input
                id="tolerance"
                type="number"
                step="0.01"
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500"
                {...register('tolerance', { valueAsNumber: true })}
              />
            </div>
            <div>
              <label
                htmlFor="price_change_threshold"
                className="mb-1 block text-sm font-medium text-slate-700"
              >
                Variação aceitável
              </label>
              <input
                id="price_change_threshold"
                type="number"
                step="0.01"
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500"
                {...register('price_change_threshold', { valueAsNumber: true })}
              />
            </div>
          </div>
          <button
            type="submit"
            className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-500"
            disabled={isRunningComparison}
          >
            {isRunningComparison ? 'Executando...' : 'Executar comparação'}
          </button>
          {comparisonError && <p className="text-sm text-red-600">{comparisonError}</p>}
          {manualResult && (
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
              <p className="mb-2 font-semibold text-slate-800">Resultado mais recente</p>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words">
                {JSON.stringify(manualResult, null, 2)}
              </pre>
            </div>
          )}
        </form>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-slate-900">Concorrentes monitorados</h2>
        {competitors.length === 0 ? (
          <p className="rounded-md border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600">
            Nenhum concorrente cadastrado até o momento.
          </p>
        ) : (
          <ul className="grid gap-4 md:grid-cols-2">
            {competitors.map((competitor) => (
              <li key={competitor.id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex flex-col gap-1 text-sm">
                  <p className="text-base font-semibold text-slate-900">{competitor.name_competitor}</p>
                  <a
                    href={competitor.product_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-slate-600 hover:text-slate-800"
                  >
                    {competitor.product_url}
                  </a>
                  <p className="text-sm text-slate-700">Preço atual: {formatCurrency(competitor.current_price)}</p>
                  {competitor.old_price && (
                    <p className="text-xs text-slate-500">
                      Preço anterior: {formatCurrency(competitor.old_price)}
                    </p>
                  )}
                  {competitor.last_checked && (
                    <p className="text-xs text-slate-500">
                      Atualizado em {new Date(competitor.last_checked).toLocaleString('pt-BR')}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-slate-900">Comparações recentes</h2>
        {comparisons.length === 0 ? (
          <p className="rounded-md border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600">
            Nenhuma comparação registrada ainda.
          </p>
        ) : (
          <ul className="space-y-3">
            {comparisons.map((comparison) => (
              <li key={comparison.id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex flex-col gap-1 text-sm">
                  <span className="font-semibold text-slate-800">
                    {new Date(comparison.timestamp).toLocaleString('pt-BR')}
                  </span>
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-700">
                    {JSON.stringify(comparison.data, null, 2)}
                  </pre>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

export default MonitoredDetailPage
