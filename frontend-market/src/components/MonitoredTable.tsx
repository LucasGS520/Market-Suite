/**
 * """ Exibe tabela com os produtos monitorados cadastrados """
 */
import { Link } from 'react-router-dom'

import { MonitoredProduct } from '../types/generated-api'

type MonitoredTableProps = {
  items: MonitoredProduct[]
}

const statusLabel: Record<string, string> = {
  active: 'Ativo',
  pending: 'Pendente',
  paused: 'Pausado',
  error: 'Erro',
}

const MonitoredTable = ({ items }: MonitoredTableProps) => {
  if (!items.length) {
    return <p className="rounded-md border border-dashed border-slate-300 bg-white p-6 text-center text-slate-600">Nenhum monitorado encontrado.</p>
  }

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <table className="min-w-full divide-y divide-slate-200">
        <thead className="bg-slate-50">
          <tr>
            <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-600">
              Nome
            </th>
            <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-600">
              Último preço
            </th>
            <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-600">
              Status
            </th>
            <th scope="col" className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200 bg-white text-sm text-slate-700">
          {items.map((item) => (
            <tr key={item.id}>
              <td className="px-4 py-3">
                <div className="flex flex-col">
                  <span className="font-semibold text-slate-900">{item.name_identification ?? 'Sem nome'}</span>
                  <a
                    href={item.product_url ?? '#'}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-slate-500 hover:text-slate-700"
                  >
                    {item.product_url ?? 'URL indisponível'}
                  </a>
                </div>
              </td>
              <td className="px-4 py-3">
                {item.current_price ? `R$ ${Number(item.current_price).toFixed(2)}` : '—'}
              </td>
              <td className="px-4 py-3">
                <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                  {statusLabel[item.status ?? 'pending'] ?? 'Pendente'}
                </span>
              </td>
              <td className="px-4 py-3 text-right">
                <Link
                  to={`/monitored/${item.id}`}
                  className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
                >
                  Ver detalhes
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default MonitoredTable
