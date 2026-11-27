interface Point {
  x: number
  y: number
}

interface SegmentOverlayProps {
  points: Point[]
  width: number
  height: number
}

/** Desenha os pontos clicados como pares (segmentos numerados) + o ponto ímpar pendente, se houver. */
export function SegmentOverlay({ points, width, height }: SegmentOverlayProps) {
  const segments: [Point, Point][] = []
  for (let i = 0; i + 1 < points.length; i += 2) {
    segments.push([points[i], points[i + 1]])
  }
  const pending = points.length % 2 === 1 ? points[points.length - 1] : null

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="pointer-events-none absolute inset-0 h-full w-full"
    >
      {segments.map(([a, b], index) => (
        <g key={`${a.x},${a.y}-${b.x},${b.y}`}>
          <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#22c55e" strokeWidth={2} />
          <circle cx={a.x} cy={a.y} r={4} fill="#22c55e" />
          <circle cx={b.x} cy={b.y} r={4} fill="#22c55e" />
          <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 6} fill="#15803d" fontSize={12}>
            {index + 1}
          </text>
        </g>
      ))}
      {pending && <circle cx={pending.x} cy={pending.y} r={4} fill="#f59e0b" />}
    </svg>
  )
}
