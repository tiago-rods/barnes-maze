import { useState } from 'react'

import { inferPose, runPoseDemo } from '@/api/pose'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FieldLabel } from '@/components/ui/field-label'
import { Input } from '@/components/ui/input'
import { useWizardState } from '@/wizard/WizardContext'

interface PoseInferStepProps {
  onBack: () => void
  /** Chamado depois de enfileirar a pose: o passo de resultados acompanha o pipeline. */
  onStarted: () => void
}

export function PoseInferStep({ onBack, onStarted }: PoseInferStepProps) {
  const { trialId } = useWizardState()
  const [modelDir, setModelDir] = useState('')
  const [device, setDevice] = useState('cpu')
  const [batchSize, setBatchSize] = useState(4)
  const [showRealModel, setShowRealModel] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function start(run: () => Promise<unknown>) {
    setError(null)
    if (trialId === null) {
      setError('Nenhum trial criado: volte ao passo anterior e clique em "Criar trial".')
      return
    }
    setBusy(true)
    try {
      await run()
      onStarted()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>3. Pose e processamento</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-zinc-600">
          A partir da pose, o resto roda sozinho em segundo plano: série x, y, θ, t → eventos por
          buraco → latência, erros, distância, eficiência e estratégia.
        </p>

        <div className="flex flex-col gap-2 rounded-md border border-amber-300 bg-amber-50 p-3">
          <p className="text-sm font-medium text-amber-900">Demonstração (sem modelo treinado)</p>
          <p className="text-sm text-amber-900">
            Gera uma trajetória <strong>sintética</strong> sobre o vídeo do trial #{trialId ?? '—'}:
            o animal fictício checa três buracos vizinhos e entra no alvo. Todo o pipeline depois
            da pose é o real. O resultado fica marcado como DEMO no banco e na tela — não é dado
            experimental.
          </p>
          <div>
            <Button disabled={busy || trialId === null} onClick={() => start(() => runPoseDemo(trialId!))}>
              Rodar demonstração
            </Button>
          </div>
        </div>

        <div className="flex flex-col gap-3 rounded-md border border-zinc-200 p-3">
          <button
            type="button"
            className="text-left text-sm font-medium text-zinc-700"
            onClick={() => setShowRealModel((v) => !v)}
          >
            {showRealModel ? '▾' : '▸'} Usar um modelo de pose treinado (US-07/08)
          </button>
          {showRealModel && (
            <>
              <p className="text-sm text-zinc-500">
                Requer o extra <code>pose</code> (SLEAP-NN/PyTorch) instalado no worker e um modelo
                treinado em <code>models/</code>.
              </p>
              <div className="grid grid-cols-3 gap-3">
                <div className="flex flex-col gap-1">
                  <FieldLabel
                    htmlFor="model-dir"
                    text="Diretório do modelo"
                    hint="Pasta do modelo de pose já treinado (US-07/08)."
                  />
                  <Input
                    id="model-dir"
                    value={modelDir}
                    onChange={(e) => setModelDir(e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <FieldLabel htmlFor="device" text="Dispositivo" hint="'cpu' ou 'cuda:0' (GPU)." />
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
              <div>
                <Button
                  variant="outline"
                  disabled={busy || !modelDir || trialId === null}
                  onClick={() =>
                    start(() =>
                      inferPose({
                        model_dir: modelDir,
                        trial_id: trialId!,
                        device,
                        batch_size: batchSize,
                      }),
                    )
                  }
                >
                  Inferir com o modelo
                </Button>
              </div>
            </>
          )}
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={onBack}>
            ← Voltar
          </Button>
          <Button variant="outline" disabled={trialId === null} onClick={onStarted}>
            Ver resultados do trial →
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
