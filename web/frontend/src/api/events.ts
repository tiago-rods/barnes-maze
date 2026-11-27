import { apiFetch } from './client'

export function enterEvents(params: { trial_id: number; config?: string; out_dir?: string }) {
  return apiFetch<{ job_id: number }>('/api/events/enter', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}
