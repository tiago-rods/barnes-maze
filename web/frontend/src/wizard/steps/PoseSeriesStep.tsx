import { useState } from 'react'

import { seriesPose } from '@/api/pose'
import { JobProgress } from '@/components/JobProgress'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export function PoseSeriesStep() {
  const [trialId, setTrialId] = useState<number | null>(null)
  const [inferenceDir, setInferenceDir] = useState('')
  const [outDir, setOutDir] = useState('data/interim')

  const [jobId, setJobId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit() {
    setError(null)
    setJobId(null)
    if (trialId === null || !inferenceDir) {
      setError('Informe o trial e o diretório da inferência.')
      return
    }
    try {
      const { job_id } = await seriesPose({
        trial_id: trialId,
        inference_dir: inferenceDir,
        out_dir: outDir,
      })
      setJobId(job_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Série de trajetória</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-zinc-600">
          Converte o `pose.csv` de uma inferência concluída na trajetória (x, y, θ, t) do trial
          (US-09/10).
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="series-trial">Trial</Label>
            <Input
              id="series-trial"
              type="number"
              value={trialId ?? ''}
              onChange={(e) => setTrialId(e.target.value ? Number(e.target.value) : null)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="inference-dir">Diretório da inferência</Label>
            <Input
              id="inference-dir"
              value={inferenceDir}
              onChange={(e) => setInferenceDir(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="out-dir">Pasta de saída</Label>
            <Input id="out-dir" value={outDir} onChange={(e) => setOutDir(e.target.value)} />
          </div>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div>
          <Button onClick={handleSubmit}>Gerar série</Button>
        </div>
        <JobProgress jobId={jobId} />
      </CardContent>
    </Card>
  )
}
