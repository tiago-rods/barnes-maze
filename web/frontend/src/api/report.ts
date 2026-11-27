import { apiFetch } from './client'

export interface Pendencia {
  trial_id: number
  motivo: string
}

export interface ExportResult {
  path: string
  count: number
  pendencias: Pendencia[]
}

export function exportTrials(params: { experiment_id: number; out_dir?: string }) {
  return apiFetch<ExportResult>('/api/report/trials', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export function exportProbes(params: { experiment_id: number; out_dir?: string }) {
  return apiFetch<ExportResult>('/api/report/probes', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export function downloadUrl(path: string) {
  return `/api/report/download?path=${encodeURIComponent(path)}`
}
