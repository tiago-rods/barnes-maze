import { apiFetch } from './client'

export interface VideoSummary {
  path: string
  name: string
}

export interface TrialInterval {
  start_s: number
  end_s: number
  start_frame: number
  end_frame: number
  manually_adjusted: boolean
}

export interface VideoInfo {
  path: string
  width: number
  height: number
  frame_count: number
  fps_declared: number
  fps_real: number
  duration_s: number
  fps_is_variable: boolean
  content_hash: string
  interval: TrialInterval
}

export function listVideos(dir?: string) {
  const query = dir ? `?dir=${encodeURIComponent(dir)}` : ''
  return apiFetch<VideoSummary[]>(`/api/videos${query}`)
}

/** Abre o Explorador de Arquivos nativo do backend; `null` se o operador cancelar. */
export function pickVideo(initialDir?: string) {
  return apiFetch<{ path: string } | null>('/api/videos/pick', {
    method: 'POST',
    body: JSON.stringify({ initial_dir: initialDir ?? null }),
  })
}

export function inspectVideo(path: string, startS?: number, endS?: number) {
  return apiFetch<VideoInfo>('/api/videos/inspect', {
    method: 'POST',
    body: JSON.stringify({ path, start_s: startS ?? null, end_s: endS ?? null }),
  })
}

export function frameUrl(path: string, frameIndex: number) {
  return `/api/videos/frame?path=${encodeURIComponent(path)}&frame_index=${frameIndex}`
}
