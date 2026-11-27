import { useEffect, useRef, useState } from 'react'

import { type JobDetail, getJob } from '@/api/jobs'

const TERMINAL_STATUSES = new Set(['finished', 'failed'])

export function useJobPolling(jobId: number | null, intervalMs = 1500) {
  const [job, setJob] = useState<JobDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | null>(null)

  useEffect(() => {
    setJob(null)
    setError(null)
    if (jobId === null) return

    let cancelled = false

    const poll = async () => {
      try {
        const result = await getJob(jobId)
        if (cancelled) return
        setJob(result)
        if (!TERMINAL_STATUSES.has(result.status)) {
          timer.current = window.setTimeout(poll, intervalMs)
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      }
    }

    poll()

    return () => {
      cancelled = true
      if (timer.current !== null) window.clearTimeout(timer.current)
    }
  }, [jobId, intervalMs])

  return { job, error }
}
