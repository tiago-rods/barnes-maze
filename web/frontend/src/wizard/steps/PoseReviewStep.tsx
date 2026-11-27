import { type PointerEvent, useState } from 'react'

import {
  type ReviewState,
  cancelReview,
  confirmSegment,
  frameUrl,
  mark,
  navigate,
  saveReview,
  selectPoint,
  startReview,
  undo,
} from '@/api/poseReview'
import { JobProgress } from '@/components/JobProgress'
import { FrameCanvas } from '@/components/canvas/FrameCanvas'
import { PoseOverlay } from '@/components/canvas/PoseOverlay'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toImagePixel } from '@/lib/imageCoords'

const POINTS = ['focinho', 'centro_corpo', 'base_cauda']

export function PoseReviewStep() {
  const [trialId, setTrialId] = useState<number | null>(null)
  const [includeReviewed, setIncludeReviewed] = useState(false)
  const [state, setState] = useState<ReviewState | null>(null)
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null)
  const [jobId, setJobId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleStart() {
    setError(null)
    setJobId(null)
    if (trialId === null) return
    try {
      setState(await startReview(trialId, includeReviewed))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function run(action: () => Promise<ReviewState>) {
    try {
      setState(await action())
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  function handleClick(event: PointerEvent<HTMLImageElement>) {
    if (trialId === null) return
    const { x, y } = toImagePixel(event)
    run(() => mark(trialId, x, y))
  }

  async function handleCancel() {
    if (trialId === null) return
    await cancelReview(trialId)
    setState(null)
    setImageSize(null)
  }

  async function handleSave() {
    if (trialId === null) return
    setError(null)
    try {
      const { job_id } = await saveReview(trialId)
      setJobId(job_id)
      setState(null)
      setImageSize(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Revisão de pose</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex items-end gap-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="review-trial">Trial</Label>
              <Input
                id="review-trial"
                type="number"
                value={trialId ?? ''}
                onChange={(e) => setTrialId(e.target.value ? Number(e.target.value) : null)}
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-zinc-600">
              <input
                type="checkbox"
                checked={includeReviewed}
                onChange={(e) => setIncludeReviewed(e.target.checked)}
              />
              Incluir trechos já revisados
            </label>
            <Button onClick={handleStart}>Iniciar revisão</Button>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <JobProgress jobId={jobId} />
        </CardContent>
      </Card>

      {state && trialId !== null && (
        <Card>
          <CardContent className="flex flex-col gap-3 pt-6">
            <p className="text-sm text-zinc-600">
              Trecho {state.segment_index + 1}/{state.segments.length}
              {state.segments[state.segment_index].confirmed ? ' (revisado)' : ' (pendente)'} ·
              quadros {state.segments[state.segment_index].start_frame}–
              {state.segments[state.segment_index].end_frame} · faltam:{' '}
              {state.segments[state.segment_index].missing_points.join(', ') || '-'}
            </p>
            <FrameCanvas
              src={frameUrl(trialId, state.frame)}
              onImageLoad={(img) =>
                setImageSize({ width: img.naturalWidth, height: img.naturalHeight })
              }
              onPointerDown={handleClick}
              overlay={
                imageSize && (
                  <PoseOverlay
                    overlay={state.overlay}
                    marks={state.marks}
                    width={imageSize.width}
                    height={imageSize.height}
                  />
                )
              }
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => run(() => navigate(trialId, 'previous_segment'))}>
                ← Trecho
              </Button>
              <Button variant="outline" size="sm" onClick={() => run(() => navigate(trialId, 'next_segment'))}>
                Trecho →
              </Button>
              <Button variant="outline" size="sm" onClick={() => run(() => navigate(trialId, 'previous_frame'))}>
                ← Quadro
              </Button>
              <span className="text-sm text-zinc-500">
                quadro {state.frame} ({state.view_range[0]}–{state.view_range[1]})
              </span>
              <Button variant="outline" size="sm" onClick={() => run(() => navigate(trialId, 'next_frame'))}>
                Quadro →
              </Button>
              <Button variant="outline" size="sm" onClick={() => run(() => undo(trialId))}>
                Desfazer
              </Button>
            </div>
            <div className="flex items-center gap-2">
              {POINTS.map((point) => (
                <Button
                  key={point}
                  size="sm"
                  variant={state.point === point ? 'default' : 'outline'}
                  onClick={() => run(() => selectPoint(trialId, point))}
                >
                  {point}
                </Button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <Button onClick={() => run(() => confirmSegment(trialId))}>Trecho revisado</Button>
              <Button variant="outline" onClick={handleCancel}>
                Cancelar
              </Button>
              <Button variant="outline" onClick={handleSave}>
                Salvar e sair
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
