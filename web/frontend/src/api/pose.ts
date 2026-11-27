import { apiFetch } from './client'

export function inferPose(params: {
  model_dir: string
  trial_id: number
  video_path?: string
  out_dir?: string
  device?: string
  batch_size?: number
}) {
  return apiFetch<{ job_id: number }>('/api/pose/infer', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export function seriesPose(params: { trial_id: number; inference_dir: string; out_dir?: string }) {
  return apiFetch<{ job_id: number }>('/api/pose/series', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}
