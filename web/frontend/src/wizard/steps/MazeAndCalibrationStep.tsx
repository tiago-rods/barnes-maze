import { type MouseEvent, type PointerEvent, useRef, useState } from 'react'

import {
  type MazeGeometry,
  createMaze,
  detectHoles,
  detectPlatform,
  generateGeometry,
  snapHoles,
} from '@/api/maze'
import { type CalibrateResult, calibrateScale } from '@/api/scale'
import { loadTrial } from '@/api/trials'
import { frameUrl } from '@/api/videos'
import { JobProgress } from '@/components/JobProgress'
import { FrameCanvas } from '@/components/canvas/FrameCanvas'
import { MazeOverlay } from '@/components/canvas/MazeOverlay'
import { SegmentOverlay } from '@/components/canvas/SegmentOverlay'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FieldLabel } from '@/components/ui/field-label'
import { Input } from '@/components/ui/input'
import { toImagePixel } from '@/lib/imageCoords'
import { useWizardState } from '@/wizard/WizardContext'

const MAX_HOLE_COUNT = 30
const MIN_HOLE_COUNT = 3
const HOLE_RADIUS_STEP_PX = 0.5
const MIN_HOLE_RADIUS_PX = 1.0

interface MazeAndCalibrationStepProps {
  onBack: () => void
  onNext: () => void
}

export function MazeAndCalibrationStep({ onBack, onNext }: MazeAndCalibrationStepProps) {
  const {
    videoPath,
    experimentId,
    mazeConfigId,
    setMazeConfigId,
    phase,
    dayNumber,
    trialNumberInDay,
    rotationDeg,
    trialId,
    setTrialId,
  } = useWizardState()

  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null)

  // --- geometria (US-04) ---
  const [name, setName] = useState('')
  const [arenaDiameterCm, setArenaDiameterCm] = useState(90)
  const [holeDiameterCm, setHoleDiameterCm] = useState(5)
  const [geometryFrameIndex, setGeometryFrameIndex] = useState(0)
  const [center, setCenter] = useState({ x: 0, y: 0 })
  const [radius, setRadius] = useState(0)
  const [startAngle, setStartAngle] = useState(0)
  const [holeCount, setHoleCount] = useState(20)
  const [holeRadius, setHoleRadius] = useState(15)
  const [targetHoleNumber, setTargetHoleNumber] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [geometry, setGeometry] = useState<MazeGeometry | null>(null)
  const [snappedCount, setSnappedCount] = useState<number | null>(null)
  const [geometryError, setGeometryError] = useState<string | null>(null)
  const rafRef = useRef<number | null>(null)

  // --- calibração (US-02) ---
  const [calibrationFrameIndex, setCalibrationFrameIndex] = useState(0)
  const [calibrationImageSize, setCalibrationImageSize] = useState<
    { width: number; height: number } | null
  >(null)
  const [points, setPoints] = useState<{ x: number; y: number }[]>([])
  const [length1Cm, setLength1Cm] = useState(20)
  const [length2Cm, setLength2Cm] = useState(20)
  const [calibration, setCalibration] = useState<CalibrateResult | null>(null)
  const [calibrationError, setCalibrationError] = useState<string | null>(null)

  // --- criar o trial ---
  const [jobId, setJobId] = useState<number | null>(null)
  const [trialError, setTrialError] = useState<string | null>(null)

  const expectedHoleAreaFraction =
    arenaDiameterCm > 0 ? (holeDiameterCm / arenaDiameterCm) ** 2 : 0

  function scheduleGeometryUpdate(
    overrides: Partial<{
      centerX: number
      centerY: number
      radius: number
      startAngle: number
      holeCount: number
      holeRadius: number
      targetHoleNumber: number
    }> = {},
  ) {
    const params = {
      center_x_px: overrides.centerX ?? center.x,
      center_y_px: overrides.centerY ?? center.y,
      platform_radius_px: overrides.radius ?? radius,
      hole_count: overrides.holeCount ?? holeCount,
      start_angle_deg: overrides.startAngle ?? startAngle,
      target_hole_number: overrides.targetHoleNumber ?? targetHoleNumber,
      hole_radius_px: overrides.holeRadius ?? holeRadius,
    }
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(() => {
      generateGeometry(params)
        .then(setGeometry)
        .catch(() => {
          // Combinação momentaneamente inválida durante o ajuste (ex. N <= 2):
          // mantém a última geometria válida, igual à janela OpenCV.
        })
    })
  }

  function handleImageLoad(image: HTMLImageElement) {
    const width = image.naturalWidth
    const height = image.naturalHeight
    setImageSize({ width, height })
    const defaultCenter = { x: width / 2, y: height / 2 }
    const defaultRadius = Math.min(width, height) * 0.35
    setCenter(defaultCenter)
    setRadius(defaultRadius)
    scheduleGeometryUpdate({
      centerX: defaultCenter.x,
      centerY: defaultCenter.y,
      radius: defaultRadius,
    })
  }

  function handlePointerDown(event: PointerEvent<HTMLImageElement>) {
    const { x, y } = toImagePixel(event)
    setCenter({ x, y })
    setDragging(true)
    scheduleGeometryUpdate({ centerX: x, centerY: y })
  }

  function handlePointerMove(event: PointerEvent<HTMLImageElement>) {
    if (!dragging) return
    const { x, y } = toImagePixel(event)
    const dx = x - center.x
    const dy = y - center.y
    const newRadius = Math.max(Math.hypot(dx, dy), 1.0)
    const newAngle = ((Math.atan2(dy, dx) * 180) / Math.PI + 360) % 360
    setRadius(newRadius)
    setStartAngle(newAngle)
    scheduleGeometryUpdate({ radius: newRadius, startAngle: newAngle })
  }

  function handlePointerUp() {
    setDragging(false)
  }

  function handleContextMenu(event: MouseEvent<HTMLImageElement>) {
    event.preventDefault()
    if (!geometry) return
    const { x, y } = toImagePixel(event)
    let nearest = geometry.holes[0]
    let nearestDist = Number.POSITIVE_INFINITY
    for (const hole of geometry.holes) {
      const dist = Math.hypot(hole.x_px - x, hole.y_px - y)
      if (dist < nearestDist) {
        nearest = hole
        nearestDist = dist
      }
    }
    if (nearestDist <= nearest.radius_px * 2) {
      setTargetHoleNumber(nearest.hole_number)
      scheduleGeometryUpdate({ targetHoleNumber: nearest.hole_number })
    }
  }

  function bumpHoleCount(delta: number) {
    const next = Math.min(Math.max(holeCount + delta, MIN_HOLE_COUNT), MAX_HOLE_COUNT)
    const nextTarget = Math.min(targetHoleNumber, next - 1)
    setHoleCount(next)
    setTargetHoleNumber(nextTarget)
    scheduleGeometryUpdate({ holeCount: next, targetHoleNumber: nextTarget })
  }

  function bumpHoleRadius(delta: number) {
    const next = Math.max(holeRadius + delta, MIN_HOLE_RADIUS_PX)
    setHoleRadius(next)
    scheduleGeometryUpdate({ holeRadius: next })
  }

  async function handleDetectPlatform() {
    if (!videoPath) return
    setGeometryError(null)
    try {
      const circle = await detectPlatform(videoPath, geometryFrameIndex)
      if (circle) {
        setCenter({ x: circle.center_x_px, y: circle.center_y_px })
        setRadius(circle.radius_px)
        scheduleGeometryUpdate({
          centerX: circle.center_x_px,
          centerY: circle.center_y_px,
          radius: circle.radius_px,
        })
      }
    } catch (err) {
      setGeometryError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleDetectHoles() {
    if (!videoPath || expectedHoleAreaFraction <= 0) return
    setGeometryError(null)
    try {
      const circle = await detectHoles(videoPath, geometryFrameIndex, expectedHoleAreaFraction)
      if (circle) {
        setCenter({ x: circle.center_x_px, y: circle.center_y_px })
        setRadius(circle.radius_px)
        scheduleGeometryUpdate({
          centerX: circle.center_x_px,
          centerY: circle.center_y_px,
          radius: circle.radius_px,
        })
      }
    } catch (err) {
      setGeometryError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleConfirmGeometry() {
    if (!videoPath || !geometry) return
    setGeometryError(null)
    try {
      const result = await snapHoles(
        geometry,
        videoPath,
        geometryFrameIndex,
        expectedHoleAreaFraction,
        2 * holeRadius,
      )
      setGeometry(result.geometry)
      setSnappedCount(result.snapped_count)
    } catch (err) {
      setGeometryError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleSaveMaze() {
    if (!geometry || experimentId === null || !name) {
      setGeometryError('Preencha o nome da montagem e confirme a geometria antes de salvar.')
      return
    }
    setGeometryError(null)
    try {
      const { maze_config_id } = await createMaze({
        experiment_id: experimentId,
        name,
        arena_diameter_cm: arenaDiameterCm,
        hole_diameter_cm: holeDiameterCm,
        geometry,
      })
      setMazeConfigId(maze_config_id)
    } catch (err) {
      setGeometryError(err instanceof Error ? err.message : String(err))
    }
  }

  function handleCalibrationClick(event: PointerEvent<HTMLImageElement>) {
    if (points.length >= 4) return
    const { x, y } = toImagePixel(event)
    setPoints((prev) => [...prev, { x, y }])
  }

  function handleUndoPoint() {
    setPoints((prev) => prev.slice(0, -1))
  }

  async function handleCalibrate() {
    if (!videoPath || mazeConfigId === null || points.length !== 4) return
    setCalibrationError(null)
    try {
      const result = await calibrateScale({
        maze_config_id: mazeConfigId,
        video_path: videoPath,
        frame_index: calibrationFrameIndex,
        segment_1: [
          [points[0].x, points[0].y],
          [points[1].x, points[1].y],
        ],
        segment_2: [
          [points[2].x, points[2].y],
          [points[3].x, points[3].y],
        ],
        length_1_cm: length1Cm,
        length_2_cm: length2Cm,
      })
      setCalibration(result)
    } catch (err) {
      setCalibrationError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleCreateTrial() {
    setTrialError(null)
    setJobId(null)
    if (!videoPath || experimentId === null || mazeConfigId === null) {
      setTrialError('Faltam dados do passo anterior — volte e confira o vídeo/experimento.')
      return
    }
    try {
      const { job_id } = await loadTrial({
        path: videoPath,
        experiment_id: experimentId,
        maze_config_id: mazeConfigId,
        phase,
        day_number: dayNumber,
        trial_number_in_day: trialNumberInDay,
        rotation_deg: rotationDeg,
      })
      setJobId(job_id)
    } catch (err) {
      setTrialError(err instanceof Error ? err.message : String(err))
    }
  }

  if (!videoPath) {
    return <p className="text-sm text-red-600">Volte ao passo 1 e escolha um vídeo primeiro.</p>
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>A. Configuração dos buracos</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <FieldLabel
                htmlFor="maze-name"
                text="Nome da montagem"
                hint="Rótulo livre para identificar esta configuração de câmera/plataforma (ex.: 'setup padrão')."
              />
              <Input id="maze-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <FieldLabel
                htmlFor="arena-diameter"
                text="Diâmetro da arena (cm)"
                hint="Medida real da plataforma física do labirinto de Barnes."
              />
              <Input
                id="arena-diameter"
                type="number"
                value={arenaDiameterCm}
                onChange={(e) => setArenaDiameterCm(Number(e.target.value))}
              />
            </div>
            <div className="flex flex-col gap-1">
              <FieldLabel
                htmlFor="hole-diameter"
                text="Diâmetro de cada buraco (cm)"
                hint="Medida real de cada buraco da plataforma."
              />
              <Input
                id="hole-diameter"
                type="number"
                value={holeDiameterCm}
                onChange={(e) => setHoleDiameterCm(Number(e.target.value))}
              />
            </div>
          </div>

          <p className="text-sm text-zinc-600">
            Arraste do centro até o buraco de referência física (vira o buraco 0). Botão direito
            perto de um buraco marca o alvo.
          </p>
          <FrameCanvas
            src={frameUrl(videoPath, geometryFrameIndex)}
            onImageLoad={handleImageLoad}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onContextMenu={handleContextMenu}
            overlay={
              imageSize && (
                <MazeOverlay geometry={geometry} width={imageSize.width} height={imageSize.height} />
              )
            }
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => bumpHoleCount(-1)}>
              − N
            </Button>
            <span className="text-sm text-zinc-500">N = {holeCount}</span>
            <Button variant="outline" size="sm" onClick={() => bumpHoleCount(1)}>
              + N
            </Button>
            <Button variant="outline" size="sm" onClick={() => bumpHoleRadius(-HOLE_RADIUS_STEP_PX)}>
              − raio
            </Button>
            <span className="text-sm text-zinc-500">raio do buraco = {holeRadius.toFixed(1)} px</span>
            <Button variant="outline" size="sm" onClick={() => bumpHoleRadius(HOLE_RADIUS_STEP_PX)}>
              + raio
            </Button>
            <Button variant="outline" size="sm" onClick={handleDetectPlatform}>
              Detectar borda
            </Button>
            <Button variant="outline" size="sm" onClick={handleDetectHoles}>
              Detectar buracos
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setGeometryFrameIndex((i) => Math.max(0, i - 1))}
            >
              ← Quadro anterior
            </Button>
            <Button variant="outline" size="sm" onClick={() => setGeometryFrameIndex((i) => i + 1)}>
              Próximo quadro →
            </Button>
          </div>
          {geometryError && <p className="text-sm text-red-600">{geometryError}</p>}
          <div className="flex items-center gap-2">
            <Button onClick={handleConfirmGeometry} disabled={!geometry}>
              Confirmar geometria
            </Button>
            {snappedCount !== null && geometry && (
              <span className="text-sm text-zinc-500">
                {snappedCount} de {geometry.holes.length} buracos ajustados automaticamente.
              </span>
            )}
          </div>
          {snappedCount !== null && (
            <div className="flex items-center gap-2">
              <Button onClick={handleSaveMaze}>Salvar montagem</Button>
              {mazeConfigId !== null && (
                <span className="text-sm text-green-700">Montagem #{mazeConfigId} salva.</span>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {mazeConfigId !== null && (
        <Card>
          <CardHeader>
            <CardTitle>B. Calibração da escala</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <p className="text-sm text-zinc-600">
              Clique 4 pontos (2 segmentos de comprimento real conhecido). {points.length}/4
              marcados.
            </p>
            <FrameCanvas
              src={frameUrl(videoPath, calibrationFrameIndex)}
              onImageLoad={(img) =>
                setCalibrationImageSize({ width: img.naturalWidth, height: img.naturalHeight })
              }
              onPointerDown={handleCalibrationClick}
              overlay={
                calibrationImageSize && (
                  <SegmentOverlay
                    points={points}
                    width={calibrationImageSize.width}
                    height={calibrationImageSize.height}
                  />
                )
              }
            />
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleUndoPoint}
                disabled={points.length === 0}
              >
                Desfazer último ponto
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCalibrationFrameIndex((i) => Math.max(0, i - 1))}
              >
                ← Quadro anterior
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCalibrationFrameIndex((i) => i + 1)}
              >
                Próximo quadro →
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <FieldLabel
                  htmlFor="length-1"
                  text="Comprimento real do segmento 1 (cm)"
                  hint="Distância real entre os dois primeiros pontos clicados."
                />
                <Input
                  id="length-1"
                  type="number"
                  value={length1Cm}
                  onChange={(e) => setLength1Cm(Number(e.target.value))}
                />
              </div>
              <div className="flex flex-col gap-1">
                <FieldLabel
                  htmlFor="length-2"
                  text="Comprimento real do segmento 2 (cm)"
                  hint="Distância real entre o 3º e o 4º pontos clicados (direção diferente do segmento 1)."
                />
                <Input
                  id="length-2"
                  type="number"
                  value={length2Cm}
                  onChange={(e) => setLength2Cm(Number(e.target.value))}
                />
              </div>
            </div>
            {calibrationError && <p className="text-sm text-red-600">{calibrationError}</p>}
            <div>
              <Button onClick={handleCalibrate} disabled={points.length !== 4}>
                Calibrar
              </Button>
            </div>
            {calibration && (
              <p className="text-sm text-green-700">
                Escala: {calibration.cm_per_px.toPrecision(6)} cm/px · divergência entre
                segmentos: {(calibration.relative_disagreement * 100).toFixed(2)}%
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {calibration && (
        <Card>
          <CardContent className="flex flex-col gap-3 pt-6">
            {trialError && <p className="text-sm text-red-600">{trialError}</p>}
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={onBack}>
                ← Voltar
              </Button>
              <Button onClick={handleCreateTrial}>Criar trial</Button>
              <Button onClick={onNext} disabled={trialId === null}>
                Continuar →
              </Button>
            </div>
            <JobProgress
              jobId={jobId}
              onFinished={(result) => {
                const id = result?.trial_id
                if (typeof id === 'number') setTrialId(id)
              }}
            />
          </CardContent>
        </Card>
      )}
    </div>
  )
}
