import { apiFetch } from './client'

type Point = [number, number]

export interface CalibrateResult {
  cm_per_px: number
  relative_disagreement: number
  angle_degrees: number
}

export interface VerifyResult {
  measured_cm: number
  known_cm: number
  relative_error: number
  accepted: boolean
}

export function calibrateScale(params: {
  maze_config_id: number
  video_path: string
  frame_index: number
  segment_1: [Point, Point]
  segment_2: [Point, Point]
  length_1_cm: number
  length_2_cm: number
}) {
  return apiFetch<CalibrateResult>('/api/scale/calibrate', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export function verifyScale(params: {
  maze_config_id: number
  video_path: string
  frame_index: number
  segment: [Point, Point]
  length_cm: number
}) {
  return apiFetch<VerifyResult>('/api/scale/verify', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}
