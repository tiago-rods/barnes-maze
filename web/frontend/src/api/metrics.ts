import { apiFetch } from './client'

export function computeDisplacement(params: { trial_id: number; ponto?: string }) {
  return apiFetch<{ job_id: number }>('/api/metrics/displacement', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}
