import { type MouseEvent, type PointerEvent, useEffect, useRef, useState } from 'react'

import { type ExperimentSummary, listExperiments } from '@/api/experiments'
import {
  type MazeGeometry,
  createMaze,
  detectHoles,
  detectPlatform,
  generateGeometry,
  snapHoles,
} from '@/api/maze'
import { type VideoSummary, frameUrl, listVideos } from '@/api/videos'
import { FrameCanvas } from '@/components/canvas/FrameCanvas'
import { MazeOverlay } from '@/components/canvas/MazeOverlay'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toImagePixel } from '@/lib/imageCoords'

const MAX_HOLE_COUNT = 30
const MIN_HOLE_COUNT = 3
const HOLE_RADIUS_STEP_PX = 0.5
const MIN_HOLE_RADIUS_PX = 1.0

export function MazeCreateStep() {
  const [dir, setDir] = useState('')
  const [videos, setVideos] = useState<VideoSummary[]>([])
  const [videoPath, setVideoPath] = useState<string | null>(null)
  const [frameIndex, setFrameIndex] = useState(0)
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null)

  const [experiments, setExperiments] = useState<ExperimentSummary[]>([])
  const [experimentId, setExperimentId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [arenaDiameterCm, setArenaDiameterCm] = useState(90)
  const [holeDiameterCm, setHoleDiameterCm] = useState(5)

  const [center, setCenter] = useState({ x: 0, y: 0 })
  const [radius, setRadius] = useState(0)
  const [startAngle, setStartAngle] = useState(0)
  const [holeCount, setHoleCount] = useState(20)
  const [holeRadius, setHoleRadius] = useState(15)
  const [targetHoleNumber, setTargetHoleNumber] = useState(0)
  const [dragging, setDragging] = useState(false)

  const [geometry, setGeometry] = useState<MazeGeometry | null>(null)
  const [snappedCount, setSnappedCount] = useState<number | null>(null)
  const [mazeConfigId, setMazeConfigId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    listExperiments()
      .then(setExperiments)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [])

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

  async function handleListVideos() {
    setError(null)
    try {
      setVideos(await listVideos(dir || undefined))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  function handleSelectVideo(path: string) {
    setVideoPath(path)
    setFrameIndex(0)
    setImageSize(null)
    setGeometry(null)
    setMazeConfigId(null)
    setSnappedCount(null)
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
    setError(null)
    try {
      const circle = await detectPlatform(videoPath, frameIndex)
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
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleDetectHoles() {
    if (!videoPath || expectedHoleAreaFraction <= 0) return
    setError(null)
    try {
      const circle = await detectHoles(videoPath, frameIndex, expectedHoleAreaFraction)
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
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleConfirm() {
    if (!videoPath || !geometry) return
    setError(null)
    try {
      const result = await snapHoles(
        geometry,
        videoPath,
        frameIndex,
        expectedHoleAreaFraction,
        2 * holeRadius,
      )
      setGeometry(result.geometry)
      setSnappedCount(result.snapped_count)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleSave() {
    if (!geometry || experimentId === null || !name) {
      setError('Preencha experimento, nome e confirme a geometria antes de salvar.')
      return
    }
    setError(null)
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
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>1. Dados da montagem</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="maze-experiment">Experimento</Label>
            <select
              id="maze-experiment"
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
            <Label htmlFor="maze-name">Nome da montagem</Label>
            <Input id="maze-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="arena-diameter">Diâmetro da arena (cm)</Label>
            <Input
              id="arena-diameter"
              type="number"
              value={arenaDiameterCm}
              onChange={(e) => setArenaDiameterCm(Number(e.target.value))}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="hole-diameter">Diâmetro de cada buraco (cm)</Label>
            <Input
              id="hole-diameter"
              type="number"
              value={holeDiameterCm}
              onChange={(e) => setHoleDiameterCm(Number(e.target.value))}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>2. Quadro de referência</CardTitle>
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
        </CardContent>
      </Card>

      {videoPath && (
        <Card>
          <CardHeader>
            <CardTitle>3. Ajustar a geometria</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <p className="text-sm text-zinc-600">
              Arraste do centro até o buraco de referência física (vira o buraco 0). Botão
              direito perto de um buraco marca o alvo.
            </p>
            <FrameCanvas
              src={frameUrl(videoPath, frameIndex)}
              onImageLoad={handleImageLoad}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onContextMenu={handleContextMenu}
              overlay={
                imageSize && (
                  <MazeOverlay
                    geometry={geometry}
                    width={imageSize.width}
                    height={imageSize.height}
                  />
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
                onClick={() => setFrameIndex((i) => Math.max(0, i - 1))}
              >
                ← Quadro anterior
              </Button>
              <Button variant="outline" size="sm" onClick={() => setFrameIndex((i) => i + 1)}>
                Próximo quadro →
              </Button>
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <div className="flex items-center gap-2">
              <Button onClick={handleConfirm} disabled={!geometry}>
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
                <Button onClick={handleSave}>Salvar montagem</Button>
                {mazeConfigId !== null && (
                  <span className="text-sm text-green-700">Montagem #{mazeConfigId} salva.</span>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
