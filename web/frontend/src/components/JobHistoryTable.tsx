import { useEffect, useState } from 'react'

import { type Job, listJobs } from '@/api/jobs'

export function JobHistoryTable() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listJobs(50)
      .then(setJobs)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [])

  if (error) return <p className="text-sm text-red-600">{error}</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-200 text-zinc-500">
            <th className="py-1 pr-3">Job</th>
            <th className="py-1 pr-3">Tipo</th>
            <th className="py-1 pr-3">Trial</th>
            <th className="py-1 pr-3">Status</th>
            <th className="py-1 pr-3">Criado em</th>
            <th className="py-1 pr-3">Erro</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id} className="border-b border-zinc-100">
              <td className="py-1 pr-3">#{job.id}</td>
              <td className="py-1 pr-3">{job.kind}</td>
              <td className="py-1 pr-3">{job.trial_id ?? '-'}</td>
              <td
                className={`py-1 pr-3 ${
                  job.status === 'failed'
                    ? 'text-red-600'
                    : job.status === 'finished'
                      ? 'text-green-700'
                      : 'text-zinc-500'
                }`}
              >
                {job.status}
              </td>
              <td className="py-1 pr-3">{new Date(job.created_at).toLocaleString()}</td>
              <td className="py-1 pr-3 text-red-600">{job.error_message ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {jobs.length === 0 && <p className="py-2 text-sm text-zinc-500">Nenhum job ainda.</p>}
    </div>
  )
}
