import { apiFetch } from './client'

export interface Hole {
  hole_number: number
  angle_deg: number
  x_px: number
  y_px: number
  radius_px: number
  is_target: boolean
}

export interface MazeGeometry {
  center_x_px: number
  center_y_px: number
  platform_radius_px: number
  holes: Hole[]
}

export interface Circle {
  center_x_px: number
  center_y_px: number
  radius_px: number
}

export function detectPlatform(videoPath: string, frameIndex: number) {
  return apiFetch<Circle | null>('/api/maze/detect-platform', {
    method: 'POST',
    body: JSON.stringify({ video_path: videoPath, frame_index: frameIndex }),
  })
}

export function detectHoles(
  videoPath: string,
  frameIndex: number,
  expectedHoleAreaFraction: number,
) {
  return apiFetch<Circle | null>('/api/maze/detect-holes', {
    method: 'POST',
    body: JSON.stringify({
      video_path: videoPath,
      frame_index: frameIndex,
      expected_hole_area_fraction: expectedHoleAreaFraction,
    }),
  })
}

export interface GenerateGeometryParams {
  center_x_px: number
  center_y_px: number
  platform_radius_px: number
  hole_count: number
  start_angle_deg: number
  target_hole_number: number
  hole_radius_px: number
}

export function generateGeometry(params: GenerateGeometryParams) {
  return apiFetch<MazeGeometry>('/api/maze/geometry', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export function snapHoles(
  geometry: MazeGeometry,
  videoPath: string,
  frameIndex: number,
  expectedHoleAreaFraction: number,
  maxOffsetPx: number,
) {
  return apiFetch<{ geometry: MazeGeometry; snapped_count: number }>('/api/maze/snap-holes', {
    method: 'POST',
    body: JSON.stringify({
      geometry,
      video_path: videoPath,
      frame_index: frameIndex,
      expected_hole_area_fraction: expectedHoleAreaFraction,
      max_offset_px: maxOffsetPx,
    }),
  })
}

export interface CreateMazeParams {
  experiment_id: number
  name: string
  arena_diameter_cm: number
  hole_diameter_cm: number
  geometry: MazeGeometry
}

export function createMaze(params: CreateMazeParams) {
  return apiFetch<{ maze_config_id: number }>('/api/maze', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}
