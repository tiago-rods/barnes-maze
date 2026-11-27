import { useState } from 'react'

import { useWizardState, WizardProvider } from '@/wizard/WizardContext'
import { MazeAndCalibrationStep } from '@/wizard/steps/MazeAndCalibrationStep'
import { PoseInferStep } from '@/wizard/steps/PoseInferStep'
import { VideoLoadStep } from '@/wizard/steps/VideoLoadStep'

type StepId = 1 | 2 | 3

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

function WizardSteps() {
  const [stepId, setStepId] = useState<StepId>(1)

  return (
    <>
      <WizardStatusBar />
      {stepId === 1 && <VideoLoadStep onNext={() => setStepId(2)} />}
      {stepId === 2 && (
        <MazeAndCalibrationStep onBack={() => setStepId(1)} onNext={() => setStepId(3)} />
      )}
      {stepId === 3 && <PoseInferStep onBack={() => setStepId(2)} />}
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
