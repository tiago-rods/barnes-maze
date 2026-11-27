import { useState } from 'react'

import { useWizardState, WizardProvider } from '@/wizard/WizardContext'
import { MazeAndCalibrationStep } from '@/wizard/steps/MazeAndCalibrationStep'
import { PoseInferStep } from '@/wizard/steps/PoseInferStep'
import { TrialResultsStep } from '@/wizard/steps/TrialResultsStep'
import { VideoLoadStep } from '@/wizard/steps/VideoLoadStep'

type StepId = 1 | 2 | 3 | 4

const STEP_LABELS: Record<StepId, string> = {
  1: 'Vídeo e trial',
  2: 'Buracos e escala',
  3: 'Pose',
  4: 'Resultados',
}

function WizardStatusBar() {
  const { experimentId, mazeConfigId, trialId } = useWizardState()
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3 rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm text-zinc-600">
      <span>Experimento: {experimentId ?? '—'}</span>
      <span>Montagem: {mazeConfigId ?? '—'}</span>
      <span>Trial: {trialId ?? '—'}</span>
    </div>
  )
}

function StepIndicator({ current }: { current: StepId }) {
  return (
    <ol className="mb-4 flex flex-wrap gap-2 text-sm">
      {(Object.keys(STEP_LABELS) as unknown as StepId[]).map((key) => {
        const id = Number(key) as StepId
        return (
          <li
            key={id}
            className={`rounded-full px-3 py-1 ${
              id === current
                ? 'bg-zinc-900 text-white'
                : id < current
                  ? 'bg-zinc-200 text-zinc-700'
                  : 'bg-zinc-100 text-zinc-400'
            }`}
          >
            {id}. {STEP_LABELS[id]}
          </li>
        )
      })}
    </ol>
  )
}

function WizardSteps() {
  const [stepId, setStepId] = useState<StepId>(1)
  const { trialId } = useWizardState()

  return (
    <>
      <StepIndicator current={stepId} />
      <WizardStatusBar />
      {stepId === 1 && <VideoLoadStep onNext={() => setStepId(2)} onUseExistingTrial={(step) => setStepId(step)} />}
      {stepId === 2 && (
        <MazeAndCalibrationStep onBack={() => setStepId(1)} onNext={() => setStepId(3)} />
      )}
      {stepId === 3 && (
        <PoseInferStep onBack={() => setStepId(2)} onStarted={() => setStepId(4)} />
      )}
      {stepId === 4 && trialId !== null && (
        <TrialResultsStep trialId={trialId} onBack={() => setStepId(3)} />
      )}
    </>
  )
}

export function SubmissionWizard() {
  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="mb-4 text-xl font-semibold">Wizard de submissão</h1>
      <WizardProvider>
        <WizardSteps />
      </WizardProvider>
    </div>
  )
}
