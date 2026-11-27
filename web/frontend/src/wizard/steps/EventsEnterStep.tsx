import { useState } from 'react'

import { enterEvents } from '@/api/events'
import { JobProgress } from '@/components/JobProgress'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export function EventsEnterStep() {
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
      const { job_id } = await enterEvents({ trial_id: trialId })
      setJobId(job_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Descoberta e entrada por buraco</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-zinc-600">
          Detecta descobertas e entradas na série do trial e grava os dois juntos numa execução
          (US-11/12/13) — a entrada depende das descobertas, por isso é um passo só.
        </p>
        <div className="flex flex-col gap-1">
          <Label htmlFor="events-trial">Trial</Label>
          <Input
            id="events-trial"
            type="number"
            value={trialId ?? ''}
            onChange={(e) => setTrialId(e.target.value ? Number(e.target.value) : null)}
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div>
          <Button onClick={handleSubmit}>Detectar eventos</Button>
        </div>
        <JobProgress jobId={jobId} />
      </CardContent>
    </Card>
  )
}
