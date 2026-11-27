import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { useWizardState, WizardProvider } from '@/wizard/WizardContext'
import { EventsEnterStep } from '@/wizard/steps/EventsEnterStep'
import { MazeCreateStep } from '@/wizard/steps/MazeCreateStep'
import { MetricsDisplacementStep } from '@/wizard/steps/MetricsDisplacementStep'
import { PoseInferStep } from '@/wizard/steps/PoseInferStep'
import { PoseReviewStep } from '@/wizard/steps/PoseReviewStep'
import { PoseSeriesStep } from '@/wizard/steps/PoseSeriesStep'
import { ScaleCalibrateStep } from '@/wizard/steps/ScaleCalibrateStep'
import { StrategyClassifyStep } from '@/wizard/steps/StrategyClassifyStep'
import { VideoLoadStep } from '@/wizard/steps/VideoLoadStep'

const STEPS = [
  { id: 'video-load', label: 'Carregar vídeo', render: () => <VideoLoadStep /> },
  { id: 'maze-create', label: 'Criar montagem', render: () => <MazeCreateStep /> },
  { id: 'scale-calibrate', label: 'Calibrar escala', render: () => <ScaleCalibrateStep /> },
  { id: 'pose-infer', label: 'Inferir pose', render: () => <PoseInferStep /> },
  { id: 'pose-series', label: 'Gerar série', render: () => <PoseSeriesStep /> },
  { id: 'pose-review', label: 'Revisar pose', render: () => <PoseReviewStep /> },
  { id: 'events-enter', label: 'Detectar eventos', render: () => <EventsEnterStep /> },
  { id: 'metrics-displacement', label: 'Métricas', render: () => <MetricsDisplacementStep /> },
  { id: 'strategy-classify', label: 'Estratégia', render: () => <StrategyClassifyStep /> },
] as const

function WizardStatusBar() {
  const { experimentId, mazeConfigId, trialId, inferenceDir, setTrialId, setMazeConfigId } =
    useWizardState()
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3 rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm text-zinc-600">
      <span>Experimento: {experimentId ?? '—'}</span>
      <span>
        Montagem: {mazeConfigId ?? '—'}
        {mazeConfigId !== null && (
          <button
            type="button"
            className="ml-1 text-xs text-zinc-400 underline"
            onClick={() => setMazeConfigId(null)}
          >
            limpar
          </button>
        )}
      </span>
      <span>
        Trial: {trialId ?? '—'}
        {trialId !== null && (
          <button
            type="button"
            className="ml-1 text-xs text-zinc-400 underline"
            onClick={() => setTrialId(null)}
          >
            limpar
          </button>
        )}
      </span>
      <span>Inferência: {inferenceDir ?? '—'}</span>
    </div>
  )
}

function WizardSteps() {
  const [stepId, setStepId] = useState<(typeof STEPS)[number]['id']>('video-load')
  const step = STEPS.find((s) => s.id === stepId) ?? STEPS[0]

  return (
    <>
      <div className="mb-4 flex flex-wrap gap-2">
        {STEPS.map((s) => (
          <Button
            key={s.id}
            variant={s.id === stepId ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStepId(s.id)}
          >
            {s.label}
          </Button>
        ))}
      </div>
      <WizardStatusBar />
      {step.render()}
    </>
  )
}

export function SubmissionWizard() {
  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="mb-4 text-xl font-semibold">Wizard de submissão</h1>
      <WizardProvider>
        <WizardSteps />
      </WizardProvider>
    </div>
  )
}
