import { useState } from 'react'

import { inferPose } from '@/api/pose'
import { JobProgress } from '@/components/JobProgress'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useWizardState } from '@/wizard/WizardContext'

export function PoseInferStep() {
  const { trialId, setTrialId, setInferenceDir } = useWizardState()
  const [modelDir, setModelDir] = useState('')
  const [videoPath, setVideoPath] = useState('')
  const [device, setDevice] = useState('cpu')
  const [batchSize, setBatchSize] = useState(4)

  const [jobId, setJobId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit() {
    setError(null)
    setJobId(null)
    if (!modelDir || trialId === null) {
      setError('Informe o diretório do modelo e o trial.')
      return
    }
    try {
      const { job_id } = await inferPose({
        model_dir: modelDir,
        trial_id: trialId,
        video_path: videoPath || undefined,
        device,
        batch_size: batchSize,
      })
      setJobId(job_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Inferência de pose</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-zinc-600">
          Pressupõe um modelo já treinado e avaliado (US-07/08) — este passo apenas roda a
          inferência sobre o vídeo do trial.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="model-dir">Diretório do modelo</Label>
            <Input id="model-dir" value={modelDir} onChange={(e) => setModelDir(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="infer-trial">Trial</Label>
            <Input
              id="infer-trial"
              type="number"
              value={trialId ?? ''}
              onChange={(e) => setTrialId(e.target.value ? Number(e.target.value) : null)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="video-path">Vídeo alternativo (opcional)</Label>
            <Input id="video-path" value={videoPath} onChange={(e) => setVideoPath(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="device">Dispositivo</Label>
            <Input id="device" value={device} onChange={(e) => setDevice(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="batch-size">Batch size</Label>
            <Input
              id="batch-size"
              type="number"
              value={batchSize}
              onChange={(e) => setBatchSize(Number(e.target.value))}
            />
          </div>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div>
          <Button onClick={handleSubmit}>Inferir</Button>
        </div>
        <JobProgress
          jobId={jobId}
          onFinished={(result) => {
            const dir = result?.run_dir
            if (typeof dir === 'string') setInferenceDir(dir)
          }}
        />
      </CardContent>
    </Card>
  )
}
