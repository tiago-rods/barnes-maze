import { useEffect, useRef } from 'react'

import { useJobPolling } from '@/hooks/useJobPolling'

interface JobProgressProps {
  jobId: number | null
  /** Chamado uma vez, quando o job termina com sucesso — para o passo repassar IDs do resultado ao próximo passo. */
  onFinished?: (result: Record<string, unknown> | null) => void
}

export function JobProgress({ jobId, onFinished }: JobProgressProps) {
  const { job, error } = useJobPolling(jobId)
  const notified = useRef<number | null>(null)
  const callback = useRef(onFinished)
  useEffect(() => {
    callback.current = onFinished
  }, [onFinished])

  // Uma vez por job: o callback costuma ser uma arrow inline (nova a cada render).
  useEffect(() => {
    if (job?.status === 'finished' && notified.current !== job.id) {
      notified.current = job.id
      callback.current?.(job.result)
    }
  }, [job])

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
