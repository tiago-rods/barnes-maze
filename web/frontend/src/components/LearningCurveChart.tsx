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
  const [event, setEvent] = useState('primary')
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
      event,
      metric,
    })
      .then(setCurves)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [experimentId, phase, event, metric])

  const animalIds = [...new Set((curves?.animals ?? []).map((point) => point.animal_id))]
  const data = (curves?.aggregate ?? []).map((point) => {
    const row: Record<string, number | null> = {
      session: point.session,
      mean: point.mean,
      sd: point.sd ?? 0,
      n_animals: point.n_animals,
    }
    for (const animal of curves?.animals ?? []) {
      if (animal.session === point.session) row[`animal_${animal.animal_id}`] = animal.mean
    }
    return row
  })
  const metricLabel = metrics.find((m) => m.key === metric)?.label ?? metric

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
        <select
          className="h-9 rounded-md border border-zinc-200 bg-white px-3 text-sm"
          value={event}
          onChange={(e) => setEvent(e.target.value)}
          aria-label="Evento"
        >
          <option value="primary">até descobrir o alvo (S→D)</option>
          <option value="total">até entrar no alvo (S→E)</option>
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
            <YAxis
              label={{ value: metricLabel, angle: -90, position: 'insideLeft', offset: 10 }}
              width={70}
            />
            <Tooltip />
            <Legend />
            {animalIds.map((id) => (
              <Line
                key={id}
                type="monotone"
                dataKey={`animal_${id}`}
                name={`Animal #${id}`}
                stroke="#a1a1aa"
                strokeDasharray="4 3"
                dot={{ r: 3 }}
                connectNulls
                isAnimationActive={false}
              />
            ))}
            <Line
              type="monotone"
              dataKey="mean"
              name="Média do grupo"
              stroke="#18181b"
              strokeWidth={2}
              dot={{ r: 5 }}
              isAnimationActive={false}
            >
              <ErrorBar dataKey="sd" width={4} strokeWidth={1} stroke="#71717a" />
            </Line>
          </LineChart>
        </ResponsiveContainer>
      </div>
      {data.length === 0 && !error && (
        <p className="text-sm text-zinc-500">
          Sem dados para esses filtros. Entram só trials com métricas consolidadas, animal
          cadastrado, evento observado (censurados ficam fora da média) e escala vigente.
        </p>
      )}
      {data.length === 1 && (
        <p className="text-sm text-zinc-500">
          Só uma sessão com dados: a curva é um único ponto. Processe trials de outros dias do
          mesmo experimento para ver a evolução.
        </p>
      )}
      {data.length > 0 && (
        <p className="text-xs text-zinc-500">
          Média por animal (cinza) e média do grupo ± DP entre animais (preto). Descritivo,
          condicionado ao sucesso — não substitui a análise de sobrevivência do laboratório.
        </p>
      )}
    </div>
  )
}
