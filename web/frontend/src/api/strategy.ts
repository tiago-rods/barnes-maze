import { apiFetch } from './client'

export function classifyStrategy(params: { trial_id: number; config?: string; out_dir?: string }) {
  return apiFetch<{ job_id: number }>('/api/strategy/classify', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}
