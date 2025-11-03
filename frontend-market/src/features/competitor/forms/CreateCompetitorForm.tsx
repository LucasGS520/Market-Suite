/**
 * """ Formulário para cadastrar concorrente associado a um monitorado """
 */
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'

import { apiClient } from '../../lib/api'

const competitorSchema = z.object({
  product_url: z.string().url('Informe uma URL válida'),
})

type CompetitorFormData = z.infer<typeof competitorSchema>

type CreateCompetitorFormProps = {
  monitoredId: string
  onCreated?: () => void
}

const CreateCompetitorForm = ({ monitoredId, onCreated }: CreateCompetitorFormProps) => {
  const [submitError, setSubmitError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
  } = useForm<CompetitorFormData>({ resolver: zodResolver(competitorSchema) })

  const onSubmit = async (formData: CompetitorFormData) => {
    setSubmitError(null)
    try {
      await apiClient.post('/competitors/scrape', {
        monitored_product_id: monitoredId,
        product_url: formData.product_url,
      })
      //Comentário: reset simplifica cadastro de múltiplos concorrentes em sequência
      reset()
      onCreated?.()
    } catch (error) {
      setSubmitError('Não foi possível agendar o concorrente. Tente novamente em instantes.')
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Adicionar concorrente</h2>
        <p className="text-sm text-slate-600">
          Informe a URL do concorrente que deseja monitorar para este produto.
        </p>
      </div>
      <div>
        <label htmlFor="competitor_url" className="mb-1 block text-sm font-medium text-slate-700">
          URL do concorrente
        </label>
        <input
          id="competitor_url"
          type="url"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500"
          placeholder="https://"
          {...register('product_url')}
        />
        {errors.product_url && <p className="mt-1 text-xs text-red-600">{errors.product_url.message}</p>}
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

export default CreateCompetitorForm
