import { apiFetch } from './client'

export type JobStatus = 'queued' | 'started' | 'finished' | 'failed'

export interface Job {
  id: number
  rq_job_id: string
  kind: string
  trial_id: number | null
  status: JobStatus
  execucao_id: number | null
  error_message: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface JobDetail extends Job {
  result: Record<string, unknown> | null
}

export function getJob(jobId: number) {
  return apiFetch<JobDetail>(`/api/jobs/${jobId}`)
}

export function listJobs(limit = 50) {
  return apiFetch<Job[]>(`/api/jobs?limit=${limit}`)
}
