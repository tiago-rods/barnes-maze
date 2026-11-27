import { useState } from 'react'
import { Link } from 'react-router-dom'

import { inferPose } from '@/api/pose'
import { JobProgress } from '@/components/JobProgress'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FieldLabel } from '@/components/ui/field-label'
import { Input } from '@/components/ui/input'
import { useWizardState } from '@/wizard/WizardContext'

interface PoseInferStepProps {
  onBack: () => void
}

export function PoseInferStep({ onBack }: PoseInferStepProps) {
  const { trialId } = useWizardState()
  const [modelDir, setModelDir] = useState('')
  const [device, setDevice] = useState('cpu')
  const [batchSize, setBatchSize] = useState(4)

  const [jobId, setJobId] = useState<number | null>(null)
  const [started, setStarted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit() {
    setError(null)
    setJobId(null)
    if (!modelDir || trialId === null) {
      setError('Informe o diretório do modelo (precisa de um trial criado no passo anterior).')
      return
    }
    try {
      const { job_id } = await inferPose({
        model_dir: modelDir,
        trial_id: trialId,
        device,
        batch_size: batchSize,
      })
      setJobId(job_id)
      setStarted(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>3. Inferência de pose (opcional)</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-zinc-600">
          Pressupõe um modelo já treinado e avaliado (US-07/08). A partir daqui, série,
          detecção de eventos, métricas e classificação de estratégia rodam sozinhos, em
          segundo plano — nada mais precisa de você. Sem um modelo agora, pode pular e voltar
          depois (o trial #{trialId} já está salvo).
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <FieldLabel
              htmlFor="model-dir"
              text="Diretório do modelo"
              hint="Pasta do modelo de pose já treinado (US-07/08)."
            />
            <Input id="model-dir" value={modelDir} onChange={(e) => setModelDir(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <FieldLabel htmlFor="device" text="Dispositivo" hint="'cpu' ou 'cuda' (GPU)." />
            <Input id="device" value={device} onChange={(e) => setDevice(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <FieldLabel
              htmlFor="batch-size"
              text="Batch size"
              hint="Quantos quadros processar por vez na inferência."
            />
            <Input
              id="batch-size"
              type="number"
              value={batchSize}
              onChange={(e) => setBatchSize(Number(e.target.value))}
            />
          </div>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={onBack}>
            ← Voltar
          </Button>
          <Button onClick={handleSubmit}>Inferir</Button>
          <Link to="/dashboard">
            <Button variant="outline">{started ? 'Ir para o Dashboard' : 'Pular esta etapa'}</Button>
          </Link>
        </div>
        <JobProgress jobId={jobId} />
        {started && (
          <p className="text-sm text-zinc-500">
            O restante do pipeline (série, eventos, métricas, estratégia) continua em segundo
            plano. Os resultados aparecem no Dashboard sob o experimento quando terminar.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
