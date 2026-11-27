interface PointXY {
  x_px: number
  y_px: number
}

interface PoseOverlayProps {
  overlay: Record<string, PointXY>
  marks: Record<string, PointXY>
  width: number
  height: number
}

const POINT_COLORS: Record<string, string> = {
  focinho: '#ef4444',
  centro_corpo: '#22c55e',
  base_cauda: '#3b82f6',
}

const POINT_INDEX: Record<string, number> = {
  focinho: 1,
  centro_corpo: 2,
  base_cauda: 3,
}

/** Pontos da série (círculo vazado) + marcações do operador (círculo cheio + número), como `_draw` na janela OpenCV. */
export function PoseOverlay({ overlay, marks, width, height }: PoseOverlayProps) {
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="pointer-events-none absolute inset-0 h-full w-full"
    >
      {Object.entries(overlay).map(([point, xy]) => (
        <circle
          key={`overlay-${point}`}
          cx={xy.x_px}
          cy={xy.y_px}
          r={5}
          fill="none"
          stroke={POINT_COLORS[point] ?? '#999'}
          strokeWidth={1.5}
        />
      ))}
      {Object.entries(marks).map(([point, xy]) => (
        <g key={`mark-${point}`}>
          <circle cx={xy.x_px} cy={xy.y_px} r={4} fill={POINT_COLORS[point] ?? '#999'} />
          <text x={xy.x_px + 6} y={xy.y_px - 6} fill={POINT_COLORS[point] ?? '#999'} fontSize={12}>
            {POINT_INDEX[point] ?? '?'}
          </text>
        </g>
      ))}
    </svg>
  )
}
