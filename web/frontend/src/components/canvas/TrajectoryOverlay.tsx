import type { MazeGeometry } from '@/api/maze'
import type { TrajectoryPoint } from '@/api/results'

interface TrajectoryOverlayProps {
  geometry: MazeGeometry
  trajectory: TrajectoryPoint[]
  /** Buracos (índice da plataforma) na ordem em que foram checados. */
  visits: number[]
  width: number
  height: number
}

/** Quebra a trajetória nos trechos sem pose: lacuna não vira reta inventada. */
function segments(points: TrajectoryPoint[]): string[] {
  const result: string[] = []
  let current: string[] = []
  for (const point of points) {
    if (point.x_px === null || point.y_px === null) {
      if (current.length > 1) result.push(current.join(' '))
      current = []
      continue
    }
    current.push(`${point.x_px.toFixed(1)},${point.y_px.toFixed(1)}`)
  }
  if (current.length > 1) result.push(current.join(' '))
  return result
}

/**
 * Trajetória do centro do corpo (US-09) sobre o quadro, com os buracos da
 * montagem, o alvo e a ordem de visitação (US-15). Desenhado em pixels da
 * imagem (`viewBox`), como `MazeOverlay`.
 */
export function TrajectoryOverlay({
  geometry,
  trajectory,
  visits,
  width,
  height,
}: TrajectoryOverlayProps) {
  const holes = new Map(geometry.holes.map((hole) => [hole.hole_number, hole]))
  const valid = trajectory.filter((p) => p.x_px !== null && p.y_px !== null)
  const start = valid[0]
  const end = valid[valid.length - 1]
  const order = new Map<number, number[]>()
  visits.forEach((hole, index) => order.set(hole, [...(order.get(hole) ?? []), index + 1]))

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="pointer-events-none absolute inset-0 h-full w-full"
    >
      <circle
        cx={geometry.center_x_px}
        cy={geometry.center_y_px}
        r={geometry.platform_radius_px}
        fill="none"
        stroke="#facc15"
        strokeOpacity={0.6}
        strokeWidth={1.5}
      />
      {geometry.holes.map((hole) => (
        <circle
          key={hole.hole_number}
          cx={hole.x_px}
          cy={hole.y_px}
          r={hole.radius_px}
          fill={hole.is_target ? 'rgba(34,197,94,0.25)' : 'none'}
          stroke={hole.is_target ? '#22c55e' : order.has(hole.hole_number) ? '#f97316' : '#a1a1aa'}
          strokeWidth={hole.is_target || order.has(hole.hole_number) ? 2.5 : 1.2}
        />
      ))}
      {segments(trajectory).map((points, index) => (
        <polyline
          key={index}
          points={points}
          fill="none"
          stroke="#3b82f6"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ))}
      {start && start.x_px !== null && start.y_px !== null && (
        <circle cx={start.x_px} cy={start.y_px} r={6} fill="#3b82f6" stroke="white" strokeWidth={2} />
      )}
      {end && end.x_px !== null && end.y_px !== null && (
        <rect
          x={end.x_px - 5}
          y={end.y_px - 5}
          width={10}
          height={10}
          fill="#1e3a8a"
          stroke="white"
          strokeWidth={2}
        />
      )}
      {[...order.entries()].map(([holeNumber, indices]) => {
        const hole = holes.get(holeNumber)
        if (!hole) return null
        const dx = hole.x_px - geometry.center_x_px
        const dy = hole.y_px - geometry.center_y_px
        const norm = Math.hypot(dx, dy) || 1
        const offset = hole.radius_px + 14
        const x = hole.x_px + (dx / norm) * offset
        const y = hole.y_px + (dy / norm) * offset
        return (
          <g key={holeNumber}>
            <circle cx={x} cy={y} r={10} fill={hole.is_target ? '#16a34a' : '#ea580c'} />
            <text
              x={x}
              y={y}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={11}
              fontWeight={700}
              fill="white"
            >
              {indices.join(',')}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
