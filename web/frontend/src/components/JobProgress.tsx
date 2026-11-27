import { useJobPolling } from '@/hooks/useJobPolling'

interface JobProgressProps {
  jobId: number | null
}

export function JobProgress({ jobId }: JobProgressProps) {
  const { job, error } = useJobPolling(jobId)

  if (jobId === null) return null
  if (error) return <p className="text-sm text-red-600">Erro ao consultar o job: {error}</p>
  if (!job) return <p className="text-sm text-zinc-500">Consultando job #{jobId}…</p>

  if (job.status === 'failed') {
    return <p className="text-sm text-red-600">Falhou: {job.error_message}</p>
  }
  if (job.status === 'finished') {
    return (
      <p className="text-sm text-green-700">
        Concluído{job.result ? ` — ${JSON.stringify(job.result)}` : ''}
      </p>
    )
  }
  return <p className="text-sm text-zinc-500">Status: {job.status}…</p>
}
