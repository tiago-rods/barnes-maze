import { apiFetch } from './client'

export interface Segment {
  start_frame: number
  end_frame: number
  missing_points: string[]
  pending: boolean
  confirmed: boolean
}

export interface PointXY {
  x_px: number
  y_px: number
}

export interface ReviewState {
  trial_id: number
  segments: Segment[]
  segment_index: number
  frame: number
  view_range: [number, number]
  point: string
  ratio: number
  marks: Record<string, PointXY>
  overlay: Record<string, PointXY>
}

type NavigateAction = 'next_segment' | 'previous_segment' | 'next_frame' | 'previous_frame'

export function startReview(trialId: number, includeReviewed = false, margin = 10) {
  return apiFetch<ReviewState>(
    `/api/pose/review/${trialId}/segments?include_reviewed=${includeReviewed}&margin=${margin}`,
  )
}

export function frameUrl(trialId: number, frameIndex: number) {
  return `/api/pose/review/${trialId}/frame/${frameIndex}`
}

export function navigate(trialId: number, action: NavigateAction) {
  return apiFetch<ReviewState>(`/api/pose/review/${trialId}/navigate`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
}

export function selectPoint(trialId: number, point: string) {
  return apiFetch<ReviewState>(`/api/pose/review/${trialId}/select-point`, {
    method: 'POST',
    body: JSON.stringify({ point }),
  })
}

export function mark(trialId: number, xPx: number, yPx: number) {
  return apiFetch<ReviewState>(`/api/pose/review/${trialId}/mark`, {
    method: 'POST',
    body: JSON.stringify({ x_px: xPx, y_px: yPx }),
  })
}

export function undo(trialId: number) {
  return apiFetch<ReviewState>(`/api/pose/review/${trialId}/undo`, { method: 'POST' })
}

export function confirmSegment(trialId: number) {
  return apiFetch<ReviewState>(`/api/pose/review/${trialId}/confirm-segment`, { method: 'POST' })
}

export function cancelReview(trialId: number) {
  return apiFetch<void>(`/api/pose/review/${trialId}/cancel`, { method: 'POST' })
}

export function saveReview(trialId: number) {
  return apiFetch<{ job_id: number }>(`/api/pose/review/${trialId}/save`, { method: 'POST' })
}
