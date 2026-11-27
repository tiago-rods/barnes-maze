import { useState } from 'react'

import { classifyStrategy } from '@/api/strategy'
import { JobProgress } from '@/components/JobProgress'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export function StrategyClassifyStep() {
  const [trialId, setTrialId] = useState<number | null>(null)
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
      const { job_id } = await classifyStrategy({ trial_id: trialId })
      setJobId(job_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Classificar estratégia de busca</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-zinc-600">
          Classifica a estratégia (espacial/serial/aleatória) a partir dos sinais da série e da
          sequência de visitação já persistida (US-20).
        </p>
        <div className="flex flex-col gap-1">
          <Label htmlFor="strategy-trial">Trial</Label>
          <Input
            id="strategy-trial"
            type="number"
            value={trialId ?? ''}
            onChange={(e) => setTrialId(e.target.value ? Number(e.target.value) : null)}
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div>
          <Button onClick={handleSubmit}>Classificar</Button>
        </div>
        <JobProgress jobId={jobId} />
      </CardContent>
    </Card>
  )
}
