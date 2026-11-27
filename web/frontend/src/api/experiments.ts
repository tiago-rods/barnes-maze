import { apiFetch } from './client'

export interface ExperimentSummary {
  id: number
  name: string
  description: string | null
  group_label: string | null
}

export function listExperiments() {
  return apiFetch<ExperimentSummary[]>('/api/experiments')
}
