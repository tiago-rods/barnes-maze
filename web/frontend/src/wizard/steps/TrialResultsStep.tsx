import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { Job } from '@/api/jobs'
import { type TrialResults, getTrialResults } from '@/api/results'
import { frameUrl } from '@/api/videos'
import { FrameCanvas } from '@/components/canvas/FrameCanvas'
import { TrajectoryOverlay } from '@/components/canvas/TrajectoryOverlay'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const POLL_MS = 2000

const STAGES: { kinds: string[]; label: string; detail: string }[] = [
  { kinds: ['pose_infer', 'pose_demo'], label: 'Pose', detail: 'US-07/08' },
  { kinds: ['pose_series'], label: 'Série x, y, θ, t', detail: 'US-09/10' },
  { kinds: ['events_enter'], label: 'Eventos por buraco', detail: 'US-11..15' },
  { kinds: ['trial_metrics'], label: 'Métricas e estratégia', detail: 'US-16..20' },
]

const STRATEGY_TEXT: Record<string, { label: string; explanation: string }> = {
  spatial: {
    label: 'Espacial',
    explanation: 'foi direto ao alvo, sem cruzar o centro e com poucos erros',
  },
  serial: {
    label: 'Serial',
    explanation: 'percorreu buracos vizinhos em sequência, no mesmo sentido, até o alvo',
  },
  random: {
    label: 'Aleatória',
    explanation: 'cruzou o centro da plataforma ou não seguiu um padrão sistemático',
  },
}

function fmt(value: number | null | undefined, digits = 1, unit = '') {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${value.toLocaleString('pt-BR', { maximumFractionDigits: digits, minimumFractionDigits: digits })}${unit}`
}

function latestJob(jobs: Job[], kinds: string[]): Job | undefined {
  return [...jobs].reverse().find((job) => kinds.includes(job.kind))
}

/**
 * O pipeline encadeia jobs (pose → série → eventos → métricas): entre um job
 * terminar e o próximo ser enfileirado, todos podem aparecer terminados por um
 * instante. Por isso "em andamento" = a última pose ainda não chegou às métricas.
 */
function pipelineInProgress(jobs: Job[]): boolean {
  if (jobs.some((job) => job.status === 'queued' || job.status === 'started')) return true
  const pose = latestJob(jobs, ['pose_infer', 'pose_demo'])
  if (!pose || pose.status === 'failed') return false
  const after = jobs.filter((job) => job.id > pose.id)
  if (after.some((job) => job.status === 'failed')) return false
  // Cadeia parada há mais de 30 s sem nada na fila: não vai continuar sozinha.
  const lastFinished = Math.max(
    ...[pose, ...after].map((job) => (job.finished_at ? Date.parse(job.finished_at) : 0)),
  )
  if (Date.now() - lastFinished > 30_000) return false
  return !after.some((job) => job.kind === 'trial_metrics' && job.status === 'finished')
}

function StatusDot({ status }: { status: string | undefined }) {
  const color =
    status === 'finished'
      ? 'bg-green-500'
      : status === 'failed'
        ? 'bg-red-500'
        : status === 'started'
          ? 'animate-pulse bg-blue-500'
          : status === 'queued'
            ? 'bg-zinc-400'
            : 'bg-zinc-200'
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${color}`} />
}

function MetricCard({
  title,
  value,
  note,
  tone = 'default',
}: {
  title: string
  value: string
  note?: string
  tone?: 'default' | 'warn'
}) {
  return (
    <div
      className={`rounded-md border p-3 ${tone === 'warn' ? 'border-amber-300 bg-amber-50' : 'border-zinc-200 bg-white'}`}
    >
      <p className="text-xs uppercase tracking-wide text-zinc-500">{title}</p>
      <p className="mt-1 text-xl font-semibold text-zinc-900">{value}</p>
      {note && <p className="mt-0.5 text-xs text-zinc-500">{note}</p>}
    </div>
  )
}

function buildConclusion(data: TrialResults): string[] {
  const row = data.results
  const report = row?.report
  if (!row || !report) return []
  const lines: string[] = []
  const lat = report.latencias
  const target = report.target_hole_number_platform

  if (lat.total_event === 1) {
    lines.push(
      `O animal entrou no buraco-alvo (#${target}) em ${fmt(lat.total_latency, 1, ' s')} após a soltura` +
        (lat.primary_event === 1
          ? `, depois de descobri-lo em ${fmt(lat.primary_latency, 1, ' s')}.`
          : '.'),
    )
  } else if (lat.primary_event === 1) {
    lines.push(
      `O animal descobriu o alvo (#${target}) em ${fmt(lat.primary_latency, 1, ' s')}, mas não chegou a entrar nele dentro do tempo limite.`,
    )
  } else if (lat.primary_event === 0) {
    lines.push(
      `O animal não encontrou o alvo dentro do tempo limite — latência censurada em ${fmt(lat.primary_latency, 0, ' s')}.`,
    )
  }

  const errors = report.erros
  if (errors.primary_errors !== null) {
    lines.push(
      errors.primary_errors === 0
        ? 'Não checou nenhum buraco errado antes do alvo.'
        : `Checou ${errors.primary_errors} buraco(s) errado(s) antes do alvo (erros primários)${errors.total_errors !== null ? `; ${errors.total_errors} no trial inteiro` : ''}.`,
    )
  }

  const displacement = report.deslocamento
  if (displacement.distance_cm !== null) {
    lines.push(
      `Percorreu ${fmt(displacement.distance_cm, 0, ' cm')} no total, a ${fmt(displacement.mean_speed_cm_s, 1, ' cm/s')} em média.`,
    )
  }

  const efficiency = report.eficiencia_rota.total_route_efficiency
  if (efficiency !== null) {
    lines.push(
      `Até entrar no alvo, a rota foi ${fmt(efficiency, 2, '×')} a distância em linha reta (1,00 = rota ideal).`,
    )
  }

  const strategy = report.estrategia.classificacao
  if (strategy && STRATEGY_TEXT[strategy]) {
    lines.push(
      `Estratégia de busca: ${STRATEGY_TEXT[strategy].label.toLowerCase()} — ${STRATEGY_TEXT[strategy].explanation}.`,
    )
  } else {
    lines.push('Estratégia de busca: não classificada (algum sinal da regra não pôde ser calculado).')
  }
  return lines
}

interface TrialResultsStepProps {
  trialId: number
  onBack?: () => void
}

export function TrialResultsStep({ trialId, onBack }: TrialResultsStepProps) {
  const [data, setData] = useState<TrialResults | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null)

  const pipelineRunning = data ? pipelineInProgress(data.jobs) : true

  useEffect(() => {
    let cancelled = false
    let timer: number | null = null
    const load = async () => {
      try {
        const result = await getTrialResults(trialId)
        if (cancelled) return
        setData(result)
        setError(null)
        if (pipelineInProgress(result.jobs)) timer = window.setTimeout(load, POLL_MS)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      }
    }
    load()
    return () => {
      cancelled = true
      if (timer !== null) window.clearTimeout(timer)
    }
  }, [trialId])

  const report = data?.results?.report ?? null
  const visits = report?.sequencia.map((item) => item.hole_number_platform) ?? []
  const conclusion = data ? buildConclusion(data) : []

  const distanceToTarget = useMemo(() => {
    if (!data?.trajectory) return []
    const target = data.geometry.holes.find((hole) => hole.is_target)
    if (!target) return []
    return data.trajectory.map((point) => ({
      t_s: Number(point.t_s.toFixed(2)),
      distancia_cm:
        point.x_px === null || point.y_px === null
          ? null
          : Number(
              (
                Math.hypot(point.x_px - target.x_px, point.y_px - target.y_px) *
                data.trial.cm_per_px
              ).toFixed(1),
            ),
    }))
  }, [data])

  if (error) return <p className="text-sm text-red-600">Erro ao carregar o trial: {error}</p>
  if (!data) return <p className="text-sm text-zinc-500">Carregando trial #{trialId}…</p>

  const row = data.results
  const lastPose = latestJob(data.jobs, ['pose_infer', 'pose_demo'])
  const failed = [...data.jobs]
    .reverse()
    .find((job) => job.status === 'failed' && (!lastPose || job.id >= lastPose.id))
  const hasMetrics = report !== null
  const lat = report?.latencias

  return (
    <div className="flex flex-col gap-4">
      {data.is_demo && (
        <div className="rounded-md border border-amber-400 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <strong>DEMONSTRAÇÃO — trajetória sintética.</strong> A pose deste trial foi gerada por
          regra fixa (modelo <code>{data.model_id}</code>), não por um modelo treinado sobre o
          vídeo. Os eventos, métricas e a estratégia abaixo são calculados pelo pipeline real, mas
          sobre um animal fictício: servem para mostrar o software, não como resultado
          experimental.
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>
            Trial #{data.trial.id} — {data.trial.filename}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <p className="text-sm text-zinc-600">
            Experimento #{data.trial.experiment_id} ({data.trial.experiment_name}) · animal{' '}
            {data.trial.animal_name ?? <span className="text-amber-700">não cadastrado</span>} ·
            fase {data.trial.phase} · dia {data.trial.day_number} · trial{' '}
            {data.trial.trial_number_in_day} no dia
          </p>
          <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {STAGES.map((stage) => {
              const job = latestJob(data.jobs, stage.kinds)
              return (
                <li key={stage.label} className="rounded-md border border-zinc-200 px-3 py-2">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <StatusDot status={job?.status} />
                    {stage.label}
                  </div>
                  <p className="text-xs text-zinc-500">
                    {stage.detail} · {job ? job.status : 'não iniciado'}
                  </p>
                </li>
              )
            })}
          </ol>
          {failed && (
            <p className="text-sm text-red-600">
              Etapa “{failed.kind}” falhou: {failed.error_message}
            </p>
          )}
          {pipelineRunning && !failed && (
            <p className="text-sm text-zinc-500">Processando em segundo plano… atualiza sozinho.</p>
          )}
          {!pipelineRunning && !hasMetrics && !failed && (
            <p className="text-sm text-zinc-500">
              Este trial ainda não tem métricas consolidadas. Volte ao passo de pose e rode a
              inferência (ou a demonstração).
            </p>
          )}
        </CardContent>
      </Card>

      {hasMetrics && report && lat && row && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Conclusão</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <ul className="list-disc space-y-1 pl-5 text-sm text-zinc-800">
                {conclusion.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              {row.is_stale && (
                <p className="text-sm text-amber-700">
                  Resultado obsoleto: a montagem foi recalibrada depois deste cálculo.
                </p>
              )}
              <p className="text-xs text-zinc-500">
                Limiares de <code>configs/default.yaml</code> — decisões da equipe, sem validação
                do laboratório (portão G3 pendente).
              </p>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <MetricCard
              title="Latência S→D"
              value={fmt(lat.primary_latency, 1, ' s')}
              note={lat.primary_event === 0 ? 'censurado (tempo limite)' : 'descoberta do alvo'}
              tone={lat.primary_event === 0 ? 'warn' : 'default'}
            />
            <MetricCard
              title="Latência S→E"
              value={fmt(lat.total_latency, 1, ' s')}
              note={lat.total_event === 0 ? 'censurado (tempo limite)' : 'entrada no alvo'}
              tone={lat.total_event === 0 ? 'warn' : 'default'}
            />
            <MetricCard
              title="Erros antes do alvo"
              value={report.erros.primary_errors === null ? '—' : String(report.erros.primary_errors)}
              note={
                report.erros.total_errors === null
                  ? undefined
                  : `${report.erros.total_errors} no trial inteiro`
              }
            />
            <MetricCard
              title="Estratégia"
              value={
                report.estrategia.classificacao
                  ? (STRATEGY_TEXT[report.estrategia.classificacao]?.label ??
                    report.estrategia.classificacao)
                  : 'não classificada'
              }
              note="regra explícita (US-20)"
            />
            <MetricCard
              title="Distância percorrida"
              value={fmt(report.deslocamento.distance_cm, 0, ' cm')}
            />
            <MetricCard
              title="Velocidade média"
              value={fmt(report.deslocamento.mean_speed_cm_s, 1, ' cm/s')}
            />
            <MetricCard
              title="Eficiência de rota"
              value={fmt(report.eficiencia_rota.total_route_efficiency, 2, '×')}
              note="percorrido ÷ linha reta (S→E)"
            />
            <MetricCard
              title="Entropia"
              value={fmt(report.entropia_bits, 2, ' bits')}
              note="ocupação angular até o alvo"
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Trajetória e ordem de visitação</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {data.trial.filepath && data.trajectory ? (
                <FrameCanvas
                  src={frameUrl(data.trial.filepath, 0)}
                  onImageLoad={(img) =>
                    setImageSize({ width: img.naturalWidth, height: img.naturalHeight })
                  }
                  overlay={
                    imageSize && (
                      <TrajectoryOverlay
                        geometry={data.geometry}
                        trajectory={data.trajectory}
                        visits={visits}
                        width={imageSize.width}
                        height={imageSize.height}
                      />
                    )
                  }
                />
              ) : (
                <p className="text-sm text-zinc-500">Trajetória indisponível.</p>
              )}
              <p className="text-xs text-zinc-500">
                Azul: trajetória do centro do corpo (● soltura, ■ fim). Laranja: buracos checados,
                numerados na ordem. Verde: alvo.
              </p>
              {report.sequencia.length > 0 && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-zinc-200 text-zinc-500">
                      <th className="py-1 pr-3">#</th>
                      <th className="py-1 pr-3">Buraco</th>
                      <th className="py-1 pr-3">Posição na sala</th>
                      <th className="py-1 pr-3">Início</th>
                      <th className="py-1 pr-3">Permanência</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.sequencia.map((item, index) => (
                      <tr
                        key={`${item.hole_number_platform}-${item.inicio_s}`}
                        className={`border-b border-zinc-100 ${item.alvo ? 'font-medium text-green-700' : ''}`}
                      >
                        <td className="py-1 pr-3">{index + 1}</td>
                        <td className="py-1 pr-3">
                          #{item.hole_number_platform}
                          {item.alvo ? ' (alvo)' : ''}
                        </td>
                        <td className="py-1 pr-3">{fmt(item.angulo_sala_deg, 0, '°')}</td>
                        <td className="py-1 pr-3">{fmt(item.inicio_s, 2, ' s')}</td>
                        <td className="py-1 pr-3">{fmt(item.dwell_s, 2, ' s')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>

          {distanceToTarget.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Distância até o alvo ao longo do trial</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={distanceToTarget} margin={{ left: 8, right: 16, bottom: 16 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis
                        dataKey="t_s"
                        type="number"
                        domain={['dataMin', 'dataMax']}
                        tickFormatter={(v: number) => `${v.toFixed(0)} s`}
                      />
                      <YAxis unit=" cm" width={64} />
                      <Tooltip
                        formatter={(value) => [`${value} cm`, 'distância']}
                        labelFormatter={(label) => `t = ${label} s`}
                      />
                      {report.sequencia.map((item) => (
                        <ReferenceLine
                          key={`${item.hole_number_platform}-${item.inicio_s}`}
                          x={Number(item.inicio_s.toFixed(2))}
                          stroke={item.alvo ? '#16a34a' : '#ea580c'}
                          strokeDasharray="4 3"
                          label={{
                            value: `#${item.hole_number_platform}`,
                            position: 'top',
                            fontSize: 11,
                          }}
                        />
                      ))}
                      <Line
                        type="monotone"
                        dataKey="distancia_cm"
                        stroke="#3b82f6"
                        dot={false}
                        strokeWidth={2}
                        connectNulls={false}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <p className="text-xs text-zinc-500">
                  Linhas tracejadas: início de cada checagem (laranja = buraco errado, verde =
                  alvo).
                </p>
              </CardContent>
            </Card>
          )}

          {report.avisos.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Avisos do cálculo</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="list-disc space-y-1 pl-5 text-sm text-zinc-600">
                  {report.avisos.map((aviso) => (
                    <li key={aviso}>{aviso}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </>
      )}

      <div className="flex gap-2">
        {onBack && (
          <Button variant="outline" onClick={onBack}>
            ← Voltar
          </Button>
        )}
        <Link to="/dashboard">
          <Button variant="outline">Ir para o Dashboard</Button>
        </Link>
      </div>
    </div>
  )
}
