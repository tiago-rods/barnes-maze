import type { ReactNode } from 'react'

interface FrameCanvasProps {
  src: string
  alt?: string
  overlay?: ReactNode
  className?: string
}

/** Quadro de vídeo + espaço para um overlay posicionado em cima (maze create, calibração, revisão de pose). */
export function FrameCanvas({ src, alt = 'Quadro do vídeo', overlay, className }: FrameCanvasProps) {
  return (
    <div className={`relative inline-block ${className ?? ''}`}>
      <img src={src} alt={alt} className="block max-w-full rounded-md border border-zinc-200" />
      {overlay}
    </div>
  )
}
