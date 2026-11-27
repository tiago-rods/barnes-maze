import { apiFetch } from './client'

export interface CatalogEntry {
  trial_id: number
  experiment_id: number
  animal: string | null
  sessao: number
  fase: string
  trial_no_dia: number
  filename: string
  filepath: string
  content_hash: string
  situacao: string
  cobertura_pose: number | null
  execucao_id: number | null
  calculado_em: string | null
  fps_variavel: boolean
  trajetoria: string | null
  file_size_bytes: number | null
  qualidade_pose: string | null
}

export function listCatalog(experimentId?: number) {
  const query = experimentId ? `?experiment_id=${experimentId}` : ''
  return apiFetch<CatalogEntry[]>(`/api/catalog${query}`)
}
