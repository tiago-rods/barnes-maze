import { createContext, type ReactNode, useContext, useState } from 'react'

interface WizardContextValue {
  videoPath: string | null
  setVideoPath: (value: string | null) => void
  experimentId: number | null
  setExperimentId: (value: number | null) => void
  mazeConfigId: number | null
  setMazeConfigId: (value: number | null) => void
  trialId: number | null
  setTrialId: (value: number | null) => void
  phase: string
  setPhase: (value: string) => void
  dayNumber: number
  setDayNumber: (value: number) => void
  trialNumberInDay: number
  setTrialNumberInDay: (value: number) => void
  rotationDeg: number
  setRotationDeg: (value: number) => void
}

const WizardContext = createContext<WizardContextValue | null>(null)

/**
 * Estado de um único trial percorrendo os 3 passos do wizard (vídeo →
 * buracos+calibração → pose). Cada passo lê o que o anterior já produziu
 * em vez de pedir de novo — o trial em si só é criado no fim do passo 2,
 * quando a montagem (US-04) finalmente existe. Série, eventos, métricas e
 * estratégia rodam automaticamente no backend a partir do passo 3 — não
 * precisam de estado aqui.
 */
export function WizardProvider({ children }: { children: ReactNode }) {
  const [videoPath, setVideoPath] = useState<string | null>(null)
  const [experimentId, setExperimentId] = useState<number | null>(null)
  const [mazeConfigId, setMazeConfigId] = useState<number | null>(null)
  const [trialId, setTrialId] = useState<number | null>(null)
  const [phase, setPhase] = useState('acquisition')
  const [dayNumber, setDayNumber] = useState(1)
  const [trialNumberInDay, setTrialNumberInDay] = useState(1)
  const [rotationDeg, setRotationDeg] = useState(0)

  return (
    <WizardContext.Provider
      value={{
        videoPath,
        setVideoPath,
        experimentId,
        setExperimentId,
        mazeConfigId,
        setMazeConfigId,
        trialId,
        setTrialId,
        phase,
        setPhase,
        dayNumber,
        setDayNumber,
        trialNumberInDay,
        setTrialNumberInDay,
        rotationDeg,
        setRotationDeg,
      }}
    >
      {children}
    </WizardContext.Provider>
  )
}

export function useWizardState(): WizardContextValue {
  const context = useContext(WizardContext)
  if (!context) {
    throw new Error('useWizardState precisa estar dentro de um <WizardProvider>.')
  }
  return context
}
