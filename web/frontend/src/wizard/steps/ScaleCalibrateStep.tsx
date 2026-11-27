import { type PointerEvent, useState } from 'react'

import { type CalibrateResult, type VerifyResult, calibrateScale, verifyScale } from '@/api/scale'
import { type VideoSummary, frameUrl, listVideos } from '@/api/videos'
import { FrameCanvas } from '@/components/canvas/FrameCanvas'
import { SegmentOverlay } from '@/components/canvas/SegmentOverlay'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toImagePixel } from '@/lib/imageCoords'
import { useWizardState } from '@/wizard/WizardContext'

type Phase = 'calibrate' | 'verify'

export function ScaleCalibrateStep() {
  const { mazeConfigId, setMazeConfigId } = useWizardState()
  const [dir, setDir] = useState('')
  const [videos, setVideos] = useState<VideoSummary[]>([])
  const [videoPath, setVideoPath] = useState<string | null>(null)
  const [frameIndex, setFrameIndex] = useState(0)
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null)

  const [phase, setPhase] = useState<Phase>('calibrate')
  const [points, setPoints] = useState<{ x: number; y: number }[]>([])

  const [length1Cm, setLength1Cm] = useState(20)
  const [length2Cm, setLength2Cm] = useState(20)
  const [lengthCm, setLengthCm] = useState(20)

  const [calibration, setCalibration] = useState<CalibrateResult | null>(null)
  const [verification, setVerification] = useState<VerifyResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const neededPoints = phase === 'calibrate' ? 4 : 2

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
    setPoints([])
  }

  function handleClick(event: PointerEvent<HTMLImageElement>) {
    if (points.length >= neededPoints) return
    const { x, y } = toImagePixel(event)
    setPoints((prev) => [...prev, { x, y }])
  }

  function handleUndo() {
    setPoints((prev) => prev.slice(0, -1))
  }

  async function handleCalibrate() {
    if (!videoPath || mazeConfigId === null || points.length !== 4) return
    setError(null)
    try {
      const result = await calibrateScale({
        maze_config_id: mazeConfigId,
        video_path: videoPath,
        frame_index: frameIndex,
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
      setPhase('verify')
      setPoints([])
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleVerify() {
    if (!videoPath || mazeConfigId === null || points.length !== 2) return
    setError(null)
    try {
      const result = await verifyScale({
        maze_config_id: mazeConfigId,
        video_path: videoPath,
        frame_index: frameIndex,
        segment: [
          [points[0].x, points[0].y],
          [points[1].x, points[1].y],
        ],
        length_cm: lengthCm,
      })
      setVerification(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>1. Montagem e quadro de referência</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="scale-maze-config">Montagem (maze_config_id)</Label>
            <Input
              id="scale-maze-config"
              type="number"
              value={mazeConfigId ?? ''}
              onChange={(e) => setMazeConfigId(e.target.value ? Number(e.target.value) : null)}
            />
          </div>
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

      {videoPath && mazeConfigId !== null && (
        <Card>
          <CardHeader>
            <CardTitle>
              2. {phase === 'calibrate' ? 'Marcar os dois segmentos conhecidos' : 'Marcar uma terceira distância independente'}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <p className="text-sm text-zinc-600">
              Clique {neededPoints} pontos ({neededPoints / 2} segmento
              {neededPoints / 2 > 1 ? 's' : ''}). {points.length}/{neededPoints} marcados.
            </p>
            <FrameCanvas
              src={frameUrl(videoPath, frameIndex)}
              onImageLoad={(img) => setImageSize({ width: img.naturalWidth, height: img.naturalHeight })}
              onPointerDown={handleClick}
              overlay={
                imageSize && (
                  <SegmentOverlay points={points} width={imageSize.width} height={imageSize.height} />
                )
              }
            />
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={handleUndo} disabled={points.length === 0}>
                Desfazer último ponto
              </Button>
              <Button variant="outline" size="sm" onClick={() => setFrameIndex((i) => Math.max(0, i - 1))}>
                ← Quadro anterior
              </Button>
              <Button variant="outline" size="sm" onClick={() => setFrameIndex((i) => i + 1)}>
                Próximo quadro →
              </Button>
            </div>

            {phase === 'calibrate' ? (
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1">
                  <Label htmlFor="length-1">Comprimento real do segmento 1 (cm)</Label>
                  <Input
                    id="length-1"
                    type="number"
                    value={length1Cm}
                    onChange={(e) => setLength1Cm(Number(e.target.value))}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <Label htmlFor="length-2">Comprimento real do segmento 2 (cm)</Label>
                  <Input
                    id="length-2"
                    type="number"
                    value={length2Cm}
                    onChange={(e) => setLength2Cm(Number(e.target.value))}
                  />
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-1">
                <Label htmlFor="length-verify">Comprimento real da terceira distância (cm)</Label>
                <Input
                  id="length-verify"
                  type="number"
                  value={lengthCm}
                  onChange={(e) => setLengthCm(Number(e.target.value))}
                />
              </div>
            )}

            {error && <p className="text-sm text-red-600">{error}</p>}

            {phase === 'calibrate' ? (
              <Button onClick={handleCalibrate} disabled={points.length !== 4}>
                Calibrar
              </Button>
            ) : (
              <Button onClick={handleVerify} disabled={points.length !== 2}>
                Verificar
              </Button>
            )}

            {calibration && (
              <p className="text-sm text-zinc-600">
                Escala: {calibration.cm_per_px.toPrecision(6)} cm/px · divergência entre
                segmentos: {(calibration.relative_disagreement * 100).toFixed(2)}%
              </p>
            )}
            {verification && (
              <p className={`text-sm ${verification.accepted ? 'text-green-700' : 'text-red-600'}`}>
                Medido: {verification.measured_cm.toPrecision(6)} cm · real:{' '}
                {verification.known_cm.toPrecision(6)} cm · erro:{' '}
                {(verification.relative_error * 100).toFixed(2)}% ·{' '}
                {verification.accepted ? 'aceito (< 3%)' : 'reprovado (≥ 3%)'}
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
