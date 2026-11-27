import type { MazeGeometry } from '@/api/maze'

interface MazeOverlayProps {
  geometry: MazeGeometry | null
  width: number
  height: number
}

/** SVG com `viewBox` nas dimensões naturais da imagem — desenha em pixels da imagem, a escala na tela é automática. */
export function MazeOverlay({ geometry, width, height }: MazeOverlayProps) {
  if (!geometry) return null
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
        stroke="yellow"
        strokeWidth={1.5}
      />
      <circle cx={geometry.center_x_px} cy={geometry.center_y_px} r={3} fill="red" />
      {geometry.holes.map((hole) => (
        <circle
          key={hole.hole_number}
          cx={hole.x_px}
          cy={hole.y_px}
          r={hole.radius_px}
          fill="none"
          stroke={hole.is_target ? '#22c55e' : hole.hole_number === 0 ? '#06b6d4' : '#f97316'}
          strokeWidth={1.5}
        />
      ))}
    </svg>
  )
}
