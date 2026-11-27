import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { MazeCreateStep } from '@/wizard/steps/MazeCreateStep'
import { PoseInferStep } from '@/wizard/steps/PoseInferStep'
import { PoseReviewStep } from '@/wizard/steps/PoseReviewStep'
import { PoseSeriesStep } from '@/wizard/steps/PoseSeriesStep'
import { ScaleCalibrateStep } from '@/wizard/steps/ScaleCalibrateStep'
import { VideoLoadStep } from '@/wizard/steps/VideoLoadStep'

const STEPS = [
  { id: 'video-load', label: 'Carregar vídeo', render: () => <VideoLoadStep /> },
  { id: 'maze-create', label: 'Criar montagem', render: () => <MazeCreateStep /> },
  { id: 'scale-calibrate', label: 'Calibrar escala', render: () => <ScaleCalibrateStep /> },
  { id: 'pose-infer', label: 'Inferir pose', render: () => <PoseInferStep /> },
  { id: 'pose-series', label: 'Gerar série', render: () => <PoseSeriesStep /> },
  { id: 'pose-review', label: 'Revisar pose', render: () => <PoseReviewStep /> },
] as const

export function SubmissionWizard() {
  const [stepId, setStepId] = useState<(typeof STEPS)[number]['id']>('video-load')
  const step = STEPS.find((s) => s.id === stepId) ?? STEPS[0]

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="mb-4 text-xl font-semibold">Wizard de submissão</h1>
      {/* Stepper simples por enquanto — os demais passos do pipeline chegam nas próximas partes. */}
      <div className="mb-4 flex gap-2">
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
      {step.render()}
    </div>
  )
}
