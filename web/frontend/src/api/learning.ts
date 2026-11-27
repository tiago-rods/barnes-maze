import { apiFetch } from './client'

export interface MetricInfo {
  key: string
  label: string
}

export interface AnimalPoint {
  animal_id: number
  session: number
  mean: number
  n_trials: number
}

export interface AggregatePoint {
  session: number
  mean: number
  sd: number | null
  n_animals: number
}

export interface LearningCurves {
  animals: AnimalPoint[]
  aggregate: AggregatePoint[]
}

export function listMetrics() {
  return apiFetch<MetricInfo[]>('/api/learning-curves/metrics')
}

export function getLearningCurves(params: {
  experimentIds?: number[]
  phase?: string
  event?: string
  metric?: string
}) {
  const query = new URLSearchParams()
  for (const id of params.experimentIds ?? []) query.append('experiment_id', String(id))
  if (params.phase) query.set('phase', params.phase)
  if (params.event) query.set('event', params.event)
  if (params.metric) query.set('metric', params.metric)
  return apiFetch<LearningCurves>(`/api/learning-curves?${query.toString()}`)
}
