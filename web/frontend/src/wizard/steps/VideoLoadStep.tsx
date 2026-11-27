import { useEffect, useState } from 'react'

import { type ExperimentSummary, listExperiments } from '@/api/experiments'
import { loadTrial } from '@/api/trials'
import { type VideoInfo, type VideoSummary, frameUrl, inspectVideo, listVideos } from '@/api/videos'
import { JobProgress } from '@/components/JobProgress'
import { FrameCanvas } from '@/components/canvas/FrameCanvas'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const PHASES = ['habituation', 'acquisition', 'probe'] as const

export function VideoLoadStep() {
  const [dir, setDir] = useState('')
  const [videos, setVideos] = useState<VideoSummary[]>([])
  const [videosError, setVideosError] = useState<string | null>(null)

  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [videoInfo, setVideoInfo] = useState<VideoInfo | null>(null)
  const [frameIndex, setFrameIndex] = useState(0)
  const [inspectError, setInspectError] = useState<string | null>(null)

  const [experiments, setExperiments] = useState<ExperimentSummary[]>([])
  const [experimentId, setExperimentId] = useState<number | null>(null)
  const [mazeConfigId, setMazeConfigId] = useState<number | null>(null)
  const [phase, setPhase] = useState<string>(PHASES[1])
  const [dayNumber, setDayNumber] = useState(1)
  const [trialNumberInDay, setTrialNumberInDay] = useState(1)
  const [rotationDeg, setRotationDeg] = useState(0)

  const [jobId, setJobId] = useState<number | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    listExperiments()
      .then(setExperiments)
      .catch((err) => setSubmitError(err instanceof Error ? err.message : String(err)))
  }, [])

  async function handleListVideos() {
    setVideosError(null)
    try {
      setVideos(await listVideos(dir || undefined))
    } catch (err) {
      setVideosError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleSelectVideo(path: string) {
    setSelectedPath(path)
    setVideoInfo(null)
    setFrameIndex(0)
    setInspectError(null)
    try {
      setVideoInfo(await inspectVideo(path))
    } catch (err) {
      setInspectError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleSubmit() {
    setSubmitError(null)
    setJobId(null)
    if (!selectedPath || experimentId === null || mazeConfigId === null) {
      setSubmitError('Selecione um vídeo, o experimento e a montagem antes de continuar.')
      return
    }
    try {
      const { job_id } = await loadTrial({
        path: selectedPath,
        experiment_id: experimentId,
        maze_config_id: mazeConfigId,
        phase,
        day_number: dayNumber,
        trial_number_in_day: trialNumberInDay,
        rotation_deg: rotationDeg,
      })
      setJobId(job_id)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>1. Escolher o vídeo</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex gap-2">
            <Input
              placeholder="Diretório (padrão: BARNES_VIDEO_DATA_DIR do backend)"
              value={dir}
              onChange={(e) => setDir(e.target.value)}
            />
            <Button onClick={handleListVideos}>Listar vídeos</Button>
          </div>
          {videosError && <p className="text-sm text-red-600">{videosError}</p>}
          <ul className="flex flex-col gap-1">
            {videos.map((video) => (
              <li key={video.path}>
                <button
                  type="button"
                  onClick={() => handleSelectVideo(video.path)}
                  className={`w-full rounded-md px-2 py-1 text-left text-sm hover:bg-zinc-100 ${
                    selectedPath === video.path ? 'bg-zinc-100 font-medium' : ''
                  }`}
                >
                  {video.name}
                </button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {selectedPath && (
        <Card>
          <CardHeader>
            <CardTitle>2. Pré-visualizar</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {inspectError && <p className="text-sm text-red-600">{inspectError}</p>}
            {videoInfo && (
              <>
                <p className="text-sm text-zinc-600">
                  {videoInfo.width}×{videoInfo.height}px · {videoInfo.fps_real.toFixed(2)} fps
                  {videoInfo.fps_is_variable ? ' (fps variável)' : ''} ·{' '}
                  {videoInfo.duration_s.toFixed(1)}s · intervalo útil{' '}
                  {videoInfo.interval.start_s.toFixed(2)}s–{videoInfo.interval.end_s.toFixed(2)}s
                </p>
                <FrameCanvas src={frameUrl(selectedPath, frameIndex)} />
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setFrameIndex((i) => Math.max(0, i - 1))}
                  >
                    ← Anterior
                  </Button>
                  <span className="text-sm text-zinc-500">
                    quadro {frameIndex} / {videoInfo.frame_count - 1}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setFrameIndex((i) => Math.min(videoInfo.frame_count - 1, i + 1))
                    }
                  >
                    Próximo →
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {selectedPath && videoInfo && (
        <Card>
          <CardHeader>
            <CardTitle>3. Registrar o trial</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <Label htmlFor="experiment">Experimento</Label>
                <select
                  id="experiment"
                  className="h-9 rounded-md border border-zinc-200 bg-white px-3 text-sm"
                  value={experimentId ?? ''}
                  onChange={(e) => setExperimentId(e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">Selecione…</option>
                  {experiments.map((exp) => (
                    <option key={exp.id} value={exp.id}>
                      #{exp.id} — {exp.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="maze-config">Montagem (maze_config_id)</Label>
                <Input
                  id="maze-config"
                  type="number"
                  value={mazeConfigId ?? ''}
                  onChange={(e) => setMazeConfigId(e.target.value ? Number(e.target.value) : null)}
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="phase">Fase</Label>
                <select
                  id="phase"
                  className="h-9 rounded-md border border-zinc-200 bg-white px-3 text-sm"
                  value={phase}
                  onChange={(e) => setPhase(e.target.value)}
                >
                  {PHASES.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="rotation">Rotação da plataforma (graus)</Label>
                <Input
                  id="rotation"
                  type="number"
                  value={rotationDeg}
                  onChange={(e) => setRotationDeg(Number(e.target.value))}
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="day">Dia (sessão)</Label>
                <Input
                  id="day"
                  type="number"
                  value={dayNumber}
                  onChange={(e) => setDayNumber(Number(e.target.value))}
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="trial-in-day">Trial no dia</Label>
                <Input
                  id="trial-in-day"
                  type="number"
                  value={trialNumberInDay}
                  onChange={(e) => setTrialNumberInDay(Number(e.target.value))}
                />
              </div>
            </div>
            {submitError && <p className="text-sm text-red-600">{submitError}</p>}
            <div>
              <Button onClick={handleSubmit}>Carregar trial</Button>
            </div>
            <JobProgress jobId={jobId} />
          </CardContent>
        </Card>
      )}
    </div>
  )
}
