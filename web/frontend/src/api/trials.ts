import { apiFetch } from './client'

export interface LoadTrialRequest {
  path: string
  experiment_id: number
  maze_config_id: number
  phase: string
  day_number: number
  trial_number_in_day: number
  rotation_deg?: number
  start_s?: number | null
  end_s?: number | null
}

export function loadTrial(request: LoadTrialRequest) {
  return apiFetch<{ job_id: number }>('/api/trials', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export interface TrialSummary {
  id: number
  maze_config_id: number
  content_hash: string | null
}

export function getTrial(trialId: number) {
  return apiFetch<TrialSummary>(`/api/trials/${trialId}`)
}
