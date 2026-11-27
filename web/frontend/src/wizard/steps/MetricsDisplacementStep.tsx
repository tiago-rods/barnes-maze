import { useState } from 'react'

import { computeDisplacement } from '@/api/metrics'
import { JobProgress } from '@/components/JobProgress'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export function MetricsDisplacementStep() {
  const [trialId, setTrialId] = useState<number | null>(null)
  const [ponto, setPonto] = useState('centro_corpo')
  const [jobId, setJobId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit() {
    setError(null)
    setJobId(null)
    if (trialId === null) {
      setError('Informe o trial.')
      return
    }
    try {
      const { job_id } = await computeDisplacement({ trial_id: trialId, ponto })
      setJobId(job_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Distância e velocidade média</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-zinc-600">
          Distância total (cm) e velocidade média (cm/s) a partir da série do trial (US-18).
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="metrics-trial">Trial</Label>
            <Input
              id="metrics-trial"
              type="number"
              value={trialId ?? ''}
              onChange={(e) => setTrialId(e.target.value ? Number(e.target.value) : null)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="ponto">Ponto do corpo</Label>
            <Input id="ponto" value={ponto} onChange={(e) => setPonto(e.target.value)} />
          </div>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div>
          <Button onClick={handleSubmit}>Calcular</Button>
        </div>
        <JobProgress jobId={jobId} />
      </CardContent>
    </Card>
  )
}
