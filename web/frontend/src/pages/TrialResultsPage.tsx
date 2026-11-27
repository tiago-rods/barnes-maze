import { useParams } from 'react-router-dom'

import { TrialResultsStep } from '@/wizard/steps/TrialResultsStep'

/** Resultados de um trial já processado, acessados pelo catálogo do Dashboard. */
export function TrialResultsPage() {
  const { trialId } = useParams()
  const id = Number(trialId)
  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="mb-4 text-xl font-semibold">Resultados do trial</h1>
      {Number.isInteger(id) && id > 0 ? (
        <TrialResultsStep trialId={id} />
      ) : (
        <p className="text-sm text-red-600">Trial inválido.</p>
      )}
    </div>
  )
}
