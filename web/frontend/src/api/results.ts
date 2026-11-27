import type { Job } from './jobs'
import type { MazeGeometry } from './maze'
import { apiFetch } from './client'

export interface TrajectoryPoint {
  t_s: number
  x_px: number | null
  y_px: number | null
}

export interface VisitReportItem {
  hole_number_platform: number
  angulo_sala_deg: number
  inicio_s: number
  dwell_s: number | null
  alvo: boolean
}

/** Relatório gravado pelo job de métricas consolidadas (`execucao.metadata.metricas_trial`). */
export interface TrialMetricsReport {
  model_id: string | null
  target_hole_number_platform: number
  latencias: {
    primary_latency: number | null
    primary_distance: number | null
    primary_event: number | null
    total_latency: number | null
    total_distance: number | null
    total_event: number | null
  }
  erros: {
    primary_errors: number | null
    total_errors: number | null
    primary_censurado: boolean | null
    criterio: string
  }
  deslocamento: {
    distance_cm: number | null
    mean_speed_cm_s: number | null
    duration_s: number | null
    interpolated_fraction: number | null
  }
  eficiencia_rota: {
    primary_route_efficiency: number | null
    total_route_efficiency: number | null
  }
  estrategia: {
    classificacao: string | null
    sinais: Record<string, unknown>
    limiares: Record<string, unknown>
    until_s: number | null
  }
  entropia_bits: number | null
  sequencia: VisitReportItem[]
  avisos: string[]
}

export interface TrialResultRow {
  id: number
  execucao_id: number
  distance_cm: number | null
  speed_mean_cm: number | null
  primary_latency_s: number | null
  total_latency_s: number | null
  primary_errors: number | null
  total_errors: number | null
  primary_event: boolean | null
  total_event: boolean | null
  entropy_bits: number | null
  search_strategy: string | null
  interpolated_fraction: number | null
  calculated_at: string | null
  is_stale: boolean
  qualidade_pose: string | null
  report: TrialMetricsReport | null
}

export interface TrialResults {
  trial: {
    id: number
    experiment_id: number
    experiment_name: string
    animal_name: string | null
    phase: string
    day_number: number
    trial_number_in_day: number
    filename: string
    filepath: string | null
    rotation_deg: number | null
    cobertura_pose: number | null
    width_px: number
    height_px: number
    fps_real: number | null
    cm_per_px: number
    interval_start_s: number | null
  }
  model_id: string | null
  is_demo: boolean
  jobs: Job[]
  results: TrialResultRow | null
  geometry: MazeGeometry
  trajectory: TrajectoryPoint[] | null
}

export function getTrialResults(trialId: number) {
  return apiFetch<TrialResults>(`/api/trials/${trialId}/results`)
}
