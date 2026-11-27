import { useEffect, useState } from 'react'

import { listCatalog } from '@/api/catalog'
import {
  type ExperimentSummary,
  createExperiment,
  createSubject,
  listExperiments,
} from '@/api/experiments'
import {
  type VideoInfo,
  type VideoSummary,
  frameUrl,
  inspectVideo,
  listVideos,
  pickVideo,
} from '@/api/videos'
import { getTrial } from '@/api/trials'
import { FrameCanvas } from '@/components/canvas/FrameCanvas'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FieldLabel } from '@/components/ui/field-label'
import { Input } from '@/components/ui/input'
import { useWizardState } from '@/wizard/WizardContext'

const PHASES = ['habituation', 'acquisition', 'probe'] as const

interface VideoLoadStepProps {
  onNext: () => void
  /** Vídeo já cadastrado como trial (mesmo hash): pula direto para pose/resultados. */
  onUseExistingTrial: (step: 3 | 4) => void
}

interface ExistingTrial {
  trialId: number
  experimentId: number
  mazeConfigId: number
  situacao: string
}

export function VideoLoadStep({ onNext, onUseExistingTrial }: VideoLoadStepProps) {
  const {
    videoPath,
    setVideoPath,
    experimentId,
    setExperimentId,
    phase,
    setPhase,
    dayNumber,
    setDayNumber,
    trialNumberInDay,
    setTrialNumberInDay,
    rotationDeg,
    setRotationDeg,
    setMazeConfigId,
    setTrialId,
  } = useWizardState()
  const [existingTrial, setExistingTrial] = useState<ExistingTrial | null>(null)

  const [dir, setDir] = useState('')
  const [videos, setVideos] = useState<VideoSummary[]>([])
  const [videosError, setVideosError] = useState<string | null>(null)

  const [videoInfo, setVideoInfo] = useState<VideoInfo | null>(null)
  const [frameIndex, setFrameIndex] = useState(0)
  const [inspectError, setInspectError] = useState<string | null>(null)

  const [experiments, setExperiments] = useState<ExperimentSummary[]>([])
  const [creatingExperiment, setCreatingExperiment] = useState(false)
  const [newExperimentName, setNewExperimentName] = useState('')
  const [newExperimentDescription, setNewExperimentDescription] = useState('')
  const [newAnimalName, setNewAnimalName] = useState('')
  const [missingAnimalName, setMissingAnimalName] = useState('')
  const [experimentError, setExperimentError] = useState<string | null>(null)

  useEffect(() => {
    listExperiments()
      .then(setExperiments)
      .catch(() => {})
  }, [])

  async function handleListVideos() {
    setVideosError(null)
    try {
      setVideos(await listVideos(dir || undefined))
    } catch (err) {
      setVideosError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handlePickVideo() {
    setVideosError(null)
    try {
      const result = await pickVideo(dir || undefined)
      if (result) handleSelectVideo(result.path)
    } catch (err) {
      setVideosError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleSelectVideo(path: string) {
    setVideoPath(path)
    setVideoInfo(null)
    setFrameIndex(0)
    setInspectError(null)
    setExistingTrial(null)
    try {
      const info = await inspectVideo(path)
      setVideoInfo(info)
      // Um vídeo só pode virar trial uma vez (hash único, US-01): se já virou,
      // oferecer o trial existente em vez de deixar "Criar trial" falhar no passo 2.
      const match = (await listCatalog()).find((row) => row.content_hash === info.content_hash)
      if (match) {
        const trial = await getTrial(match.trial_id)
        setExistingTrial({
          trialId: match.trial_id,
          experimentId: match.experiment_id,
          mazeConfigId: trial.maze_config_id,
          situacao: match.situacao,
        })
      }
    } catch (err) {
      setInspectError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleCreateExperiment() {
    setExperimentError(null)
    if (!newExperimentName.trim()) {
      setExperimentError('Informe um nome para o experimento.')
      return
    }
    if (!newAnimalName.trim()) {
      setExperimentError('Informe o animal: sem ele o trial não entra nas curvas de aprendizado.')
      return
    }
    try {
      const { experiment_id } = await createExperiment({
        name: newExperimentName.trim(),
        description: newExperimentDescription.trim() || undefined,
        animal_name: newAnimalName.trim(),
      })
      setExperiments(await listExperiments())
      setExperimentId(experiment_id)
      setCreatingExperiment(false)
      setNewExperimentName('')
      setNewExperimentDescription('')
      setNewAnimalName('')
    } catch (err) {
      setExperimentError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleRegisterAnimal(targetExperimentId: number | null) {
    setExperimentError(null)
    if (targetExperimentId === null || !missingAnimalName.trim()) {
      setExperimentError('Informe o nome do animal.')
      return
    }
    try {
      await createSubject(targetExperimentId, missingAnimalName.trim())
      setExperiments(await listExperiments())
      setMissingAnimalName('')
    } catch (err) {
      setExperimentError(err instanceof Error ? err.message : String(err))
    }
  }

  const selectedExperiment = experiments.find((exp) => exp.id === experimentId) ?? null

  const canContinue = videoPath !== null && videoInfo !== null && experimentId !== null

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>1. Vídeo e experimento</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div>
            <Button onClick={handlePickVideo}>Abrir Explorador de Arquivos…</Button>
          </div>
          <p className="text-sm text-zinc-500">Ou liste os vídeos de uma pasta específica:</p>
          <div className="flex gap-2">
            <Input
              placeholder="Diretório (padrão: BARNES_VIDEO_DATA_DIR do backend)"
              value={dir}
              onChange={(e) => setDir(e.target.value)}
            />
            <Button variant="outline" onClick={handleListVideos}>
              Listar vídeos
            </Button>
          </div>
          {videosError && <p className="text-sm text-red-600">{videosError}</p>}
          <ul className="flex flex-col gap-1">
            {videos.map((video) => (
              <li key={video.path}>
                <button
                  type="button"
                  onClick={() => handleSelectVideo(video.path)}
                  className={`w-full rounded-md px-2 py-1 text-left text-sm hover:bg-zinc-100 ${
                    videoPath === video.path ? 'bg-zinc-100 font-medium' : ''
                  }`}
                >
                  {video.name}
                </button>
              </li>
            ))}
          </ul>

          {inspectError && <p className="text-sm text-red-600">{inspectError}</p>}
          {videoInfo && videoPath && (
            <>
              <p className="text-sm text-zinc-600">
                {videoInfo.width}×{videoInfo.height}px · {videoInfo.fps_real.toFixed(2)} fps
                {videoInfo.fps_is_variable ? ' (fps variável)' : ''} ·{' '}
                {videoInfo.duration_s.toFixed(1)}s · intervalo útil{' '}
                {videoInfo.interval.start_s.toFixed(2)}s–{videoInfo.interval.end_s.toFixed(2)}s
              </p>
              <FrameCanvas src={frameUrl(videoPath, frameIndex)} />
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setFrameIndex((i) => Math.max(0, i - 1))}
                >
                  ← Anterior
                </Button>
                <FieldLabel
                  htmlFor="frame-index"
                  text="Quadro"
                  hint="Número do quadro exibido (0 = primeiro quadro do vídeo)."
                />
                <Input
                  id="frame-index"
                  type="number"
                  className="w-24"
                  min={0}
                  max={videoInfo.frame_count - 1}
                  value={frameIndex}
                  onChange={(e) => {
                    const next = Number(e.target.value)
                    if (!Number.isNaN(next)) {
                      setFrameIndex(Math.min(Math.max(0, next), videoInfo.frame_count - 1))
                    }
                  }}
                />
                <span className="text-sm text-zinc-500">/ {videoInfo.frame_count - 1}</span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setFrameIndex((i) => Math.min(videoInfo.frame_count - 1, i + 1))}
                >
                  Próximo →
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {existingTrial && (
        <Card>
          <CardContent className="flex flex-col gap-3 pt-6">
            <p className="text-sm text-zinc-700">
              Este vídeo já está cadastrado como <strong>trial #{existingTrial.trialId}</strong>{' '}
              (experimento #{existingTrial.experimentId}, montagem #{existingTrial.mazeConfigId},
              situação: {existingTrial.situacao}). Um mesmo vídeo não pode virar dois trials.
            </p>
            {(() => {
              const experiment = experiments.find((exp) => exp.id === existingTrial.experimentId)
              if (!experiment || experiment.animal_name) return null
              return (
                <div className="flex flex-col gap-2 rounded-md border border-amber-300 bg-amber-50 p-3">
                  <p className="text-sm text-amber-900">
                    O experimento #{experiment.id} não tem animal cadastrado — sem ele este trial
                    não aparece nas curvas de aprendizado (US-22).
                  </p>
                  <div className="flex gap-2">
                    <Input
                      aria-label="Nome do animal"
                      placeholder="Nome do animal"
                      value={missingAnimalName}
                      onChange={(e) => setMissingAnimalName(e.target.value)}
                    />
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => handleRegisterAnimal(experiment.id)}
                    >
                      Cadastrar animal
                    </Button>
                  </div>
                  {experimentError && <p className="text-sm text-red-600">{experimentError}</p>}
                </div>
              )
            })()}
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => {
                  setExperimentId(existingTrial.experimentId)
                  setMazeConfigId(existingTrial.mazeConfigId)
                  setTrialId(existingTrial.trialId)
                  onUseExistingTrial(3)
                }}
              >
                Usar este trial → pose
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setExperimentId(existingTrial.experimentId)
                  setMazeConfigId(existingTrial.mazeConfigId)
                  setTrialId(existingTrial.trialId)
                  onUseExistingTrial(4)
                }}
              >
                Ver resultados do trial #{existingTrial.trialId}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {videoPath && videoInfo && !existingTrial && (
        <Card>
          <CardHeader>
            <CardTitle>2. Dados do trial</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <FieldLabel
                  htmlFor="experiment"
                  text="Experimento"
                  hint="Experimento ao qual este trial pertence. Use 'Novo experimento' para criar um."
                />
                <div className="flex gap-2">
                  <select
                    id="experiment"
                    className="h-9 flex-1 rounded-md border border-zinc-200 bg-white px-3 text-sm"
                    value={experimentId ?? ''}
                    onChange={(e) =>
                      setExperimentId(e.target.value ? Number(e.target.value) : null)
                    }
                  >
                    <option value="">Selecione…</option>
                    {experiments.map((exp) => (
                      <option key={exp.id} value={exp.id}>
                        #{exp.id} — {exp.name}
                        {exp.animal_name ? ` (${exp.animal_name})` : ' (sem animal)'}
                      </option>
                    ))}
                  </select>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setCreatingExperiment((v) => !v)}
                  >
                    {creatingExperiment ? 'Cancelar' : 'Novo experimento'}
                  </Button>
                </div>
              </div>
              <div className="flex flex-col gap-1">
                <FieldLabel
                  htmlFor="phase"
                  text="Fase"
                  hint="Etapa do protocolo: habituation (habituação), acquisition (aquisição) ou probe (teste sem o alvo)."
                />
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
            </div>

            {creatingExperiment && (
              <div className="flex flex-col gap-3 rounded-md border border-zinc-200 bg-zinc-50 p-3">
                <div className="flex flex-col gap-1">
                  <FieldLabel
                    htmlFor="new-experiment-name"
                    text="Nome do novo experimento"
                    hint="Nome livre para identificar o experimento (ex.: 'Grupo WT — novembro')."
                  />
                  <Input
                    id="new-experiment-name"
                    value={newExperimentName}
                    onChange={(e) => setNewExperimentName(e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <FieldLabel
                    htmlFor="new-animal-name"
                    text="Animal"
                    hint="Identificação do animal deste experimento (1 experimento = 1 animal)."
                  />
                  <Input
                    id="new-animal-name"
                    value={newAnimalName}
                    onChange={(e) => setNewAnimalName(e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <FieldLabel
                    htmlFor="new-experiment-description"
                    text="Descrição (opcional)"
                    hint="Descrição livre, opcional."
                  />
                  <Input
                    id="new-experiment-description"
                    value={newExperimentDescription}
                    onChange={(e) => setNewExperimentDescription(e.target.value)}
                  />
                </div>
                {experimentError && <p className="text-sm text-red-600">{experimentError}</p>}
                <div>
                  <Button type="button" onClick={handleCreateExperiment}>
                    Criar experimento
                  </Button>
                </div>
              </div>
            )}

            {selectedExperiment && !selectedExperiment.animal_name && !creatingExperiment && (
              <div className="flex flex-col gap-2 rounded-md border border-amber-300 bg-amber-50 p-3">
                <p className="text-sm text-amber-900">
                  O experimento #{selectedExperiment.id} não tem animal cadastrado — os trials dele
                  não aparecem nas curvas de aprendizado (US-22).
                </p>
                <div className="flex gap-2">
                  <Input
                    aria-label="Nome do animal"
                    placeholder="Nome do animal"
                    value={missingAnimalName}
                    onChange={(e) => setMissingAnimalName(e.target.value)}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => handleRegisterAnimal(experimentId)}
                  >
                    Cadastrar animal
                  </Button>
                </div>
              </div>
            )}
            {experimentError && !creatingExperiment && (
              <p className="text-sm text-red-600">{experimentError}</p>
            )}

            <div className="grid grid-cols-3 gap-3">
              <div className="flex flex-col gap-1">
                <FieldLabel
                  htmlFor="rotation"
                  text="Rotação da plataforma (graus)"
                  hint="Rotação da plataforma física, em graus — usada para converter o buraco alvo entre o referencial da imagem e o da sala (US-05)."
                />
                <Input
                  id="rotation"
                  type="number"
                  value={rotationDeg}
                  onChange={(e) => setRotationDeg(Number(e.target.value))}
                />
              </div>
              <div className="flex flex-col gap-1">
                <FieldLabel
                  htmlFor="day"
                  text="Dia (sessão)"
                  hint="Número do dia/sessão do trial dentro do experimento (1, 2, 3...)."
                />
                <Input
                  id="day"
                  type="number"
                  value={dayNumber}
                  onChange={(e) => setDayNumber(Number(e.target.value))}
                />
              </div>
              <div className="flex flex-col gap-1">
                <FieldLabel
                  htmlFor="trial-in-day"
                  text="Trial no dia"
                  hint="Ordem deste trial dentro do dia (1º trial do dia = 1, 2º = 2...)."
                />
                <Input
                  id="trial-in-day"
                  type="number"
                  value={trialNumberInDay}
                  onChange={(e) => setTrialNumberInDay(Number(e.target.value))}
                />
              </div>
            </div>

            <div>
              <Button onClick={onNext} disabled={!canContinue}>
                Continuar →
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
