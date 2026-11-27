import { createContext, type ReactNode, useContext, useState } from 'react'

interface WizardContextValue {
  experimentId: number | null
  setExperimentId: (value: number | null) => void
  mazeConfigId: number | null
  setMazeConfigId: (value: number | null) => void
  trialId: number | null
  setTrialId: (value: number | null) => void
  inferenceDir: string | null
  setInferenceDir: (value: string | null) => void
}

const WizardContext = createContext<WizardContextValue | null>(null)

/**
 * IDs que um passo produz e o próximo reaproveita (experimento, montagem,
 * trial, diretório de inferência) — editáveis em qualquer passo, mas
 * compartilhados entre todos, para não exigir copiar e colar entre eles.
 */
export function WizardProvider({ children }: { children: ReactNode }) {
  const [experimentId, setExperimentId] = useState<number | null>(null)
  const [mazeConfigId, setMazeConfigId] = useState<number | null>(null)
  const [trialId, setTrialId] = useState<number | null>(null)
  const [inferenceDir, setInferenceDir] = useState<string | null>(null)

  return (
    <WizardContext.Provider
      value={{
        experimentId,
        setExperimentId,
        mazeConfigId,
        setMazeConfigId,
        trialId,
        setTrialId,
        inferenceDir,
        setInferenceDir,
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
