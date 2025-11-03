/**
 * """ Formulário para cadastrar produtos monitorados via scraping """
 */
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'

import { apiClient } from '../../lib/api'
import { CreateMonitoredDto } from '../../../types/generated-api'

const monitoredSchema = z.object({
  name_identification: z.string().min(2, 'Informe um nome descritivo'),
  product_url: z.string().url('Informe uma URL válida'),
  target_price: z.preprocess((value) => {
    if (value === '' || value === null || value === undefined) {
      return undefined
    }
    if (typeof value === 'string') {
      return Number(value.replace(',', '.'))
    }
    return value
  }, z.number().positive('Preço deve ser maior que zero')),
})

type MonitoredFormData = z.infer<typeof monitoredSchema>

type CreateMonitoredFormProps = {
  onCreated?: () => void
}

const CreateMonitoredForm = ({ onCreated }: CreateMonitoredFormProps) => {
  const [submitError, setSubmitError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
  } = useForm<MonitoredFormData>({ resolver: zodResolver(monitoredSchema) })

  const onSubmit = async (formData: MonitoredFormData) => {
    setSubmitError(null)
    try {
      const payload: CreateMonitoredDto = {
        name_identification: formData.name_identification,
        product_url: formData.product_url,
        target_price: formData.target_price,
      }
      await apiClient.post('/monitored/scrape', payload)
      //Comentário: resetamos após agendar para incentivar novas entradas consecutivas
      reset()
      onCreated?.()
    } catch (error) {
      setSubmitError('Não foi possível agendar o scraping. Tente novamente em instantes.')
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Novo monitorado</h2>
        <p className="text-sm text-slate-600">
          Informe o link do produto a ser monitorado. A coleta ocorrerá em seguida.
        </p>
      </div>
      <div>
        <label htmlFor="name_identification" className="mb-1 block text-sm font-medium text-slate-700">
          Nome interno
        </label>
        <input
          id="name_identification"
          type="text"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500"
          {...register('name_identification')}
        />
        {errors.name_identification && (
          <p className="mt-1 text-xs text-red-600">{errors.name_identification.message}</p>
        )}
      </div>
      <div>
        <label htmlFor="product_url" className="mb-1 block text-sm font-medium text-slate-700">
          URL do produto
        </label>
        <input
          id="product_url"
          type="url"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500"
          placeholder="https://"
          {...register('product_url')}
        />
        {errors.product_url && <p className="mt-1 text-xs text-red-600">{errors.product_url.message}</p>}
      </div>
      <div>
        <label htmlFor="target_price" className="mb-1 block text-sm font-medium text-slate-700">
          Preço alvo
        </label>
        <input
          id="target_price"
          type="number"
          step="0.01"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500"
          {...register('target_price')}
        />
        {errors.target_price && <p className="mt-1 text-xs text-red-600">{errors.target_price.message}</p>}
      </div>
      <button
        type="submit"
        className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-500"
        disabled={isSubmitting}
      >
        {isSubmitting ? 'Agendando...' : 'Agendar scraping'}
      </button>
      {submitError && <p className="text-sm text-red-600">{submitError}</p>}
    </form>
  )
}

export default CreateMonitoredForm