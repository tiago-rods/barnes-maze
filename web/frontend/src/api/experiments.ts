import { apiFetch } from './client'

export interface ExperimentSummary {
  id: number
  name: string
  description: string | null
  group_label: string | null
  /** Animal do experimento (1:1). Sem ele, o trial não aparece nas curvas (US-22). */
  animal_name: string | null
}

export function listExperiments() {
  return apiFetch<ExperimentSummary[]>('/api/experiments')
}

export function createExperiment(params: {
  name: string
  description?: string
  animal_name?: string
}) {
  return apiFetch<{ experiment_id: number }>('/api/experiments', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export function createSubject(experimentId: number, name: string) {
  return apiFetch<void>(`/api/experiments/${experimentId}/subject`, {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}
