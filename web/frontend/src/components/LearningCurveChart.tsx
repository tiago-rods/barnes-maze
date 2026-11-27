import { useEffect, useState } from 'react'
import {
  CartesianGrid,
  ErrorBar,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  type LearningCurves,
  type MetricInfo,
  getLearningCurves,
  listMetrics,
} from '@/api/learning'

interface LearningCurveChartProps {
  experimentId?: number
}

export function LearningCurveChart({ experimentId }: LearningCurveChartProps) {
  const [metrics, setMetrics] = useState<MetricInfo[]>([])
  const [metric, setMetric] = useState('latency')
  const [phase, setPhase] = useState('acquisition')
  const [curves, setCurves] = useState<LearningCurves | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listMetrics()
      .then(setMetrics)
      .catch(() => {})
  }, [])

  useEffect(() => {
    setError(null)
    getLearningCurves({
      experimentIds: experimentId ? [experimentId] : undefined,
      phase,
      metric,
    })
      .then(setCurves)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [experimentId, phase, metric])

  const data = (curves?.aggregate ?? []).map((point) => ({
    session: point.session,
    mean: point.mean,
    sd: point.sd ?? 0,
    n_animals: point.n_animals,
  }))

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        <select
          className="h-9 rounded-md border border-zinc-200 bg-white px-3 text-sm"
          value={metric}
          onChange={(e) => setMetric(e.target.value)}
        >
          {metrics.map((m) => (
            <option key={m.key} value={m.key}>
              {m.label}
            </option>
          ))}
        </select>
        <select
          className="h-9 rounded-md border border-zinc-200 bg-white px-3 text-sm"
          value={phase}
          onChange={(e) => setPhase(e.target.value)}
        >
          <option value="habituation">habituation</option>
          <option value="acquisition">acquisition</option>
          <option value="probe">probe</option>
        </select>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="session"
              label={{ value: 'Sessão', position: 'insideBottom', offset: -5 }}
            />
            <YAxis />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="mean" name="Média do grupo" stroke="#18181b" dot>
              <ErrorBar dataKey="sd" width={4} strokeWidth={1} stroke="#71717a" />
            </Line>
          </LineChart>
        </ResponsiveContainer>
      </div>
      {data.length === 0 && !error && (
        <p className="text-sm text-zinc-500">Sem dados para esses filtros.</p>
      )}
    </div>
  )
}
