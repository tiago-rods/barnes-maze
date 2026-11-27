import { forwardRef, type MouseEvent, type PointerEvent, type ReactNode } from 'react'

interface FrameCanvasProps {
  src: string
  alt?: string
  overlay?: ReactNode
  className?: string
  onImageLoad?: (image: HTMLImageElement) => void
  onPointerDown?: (event: PointerEvent<HTMLImageElement>) => void
  onPointerMove?: (event: PointerEvent<HTMLImageElement>) => void
  onPointerUp?: (event: PointerEvent<HTMLImageElement>) => void
  onContextMenu?: (event: MouseEvent<HTMLImageElement>) => void
}

/**
 * Quadro de vídeo + espaço para um overlay posicionado em cima (maze create,
 * calibração, revisão de pose). O `ref` aponta para o `<img>` — natural
 * width/height dele é a base para converter cliques em pixels da imagem
 * original (ver `lib/imageCoords.ts`), já que a exibição pode estar
 * reduzida por CSS.
 */
export const FrameCanvas = forwardRef<HTMLImageElement, FrameCanvasProps>(function FrameCanvas(
  { src, alt = 'Quadro do vídeo', overlay, className, onImageLoad, onPointerDown, onPointerMove, onPointerUp, onContextMenu },
  ref,
) {
  return (
    <div className={`relative inline-block ${className ?? ''}`}>
      <img
        ref={ref}
        src={src}
        alt={alt}
        draggable={false}
        className="block max-w-full rounded-md border border-zinc-200"
        onLoad={(e) => onImageLoad?.(e.currentTarget)}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onContextMenu={onContextMenu}
      />
      {overlay}
    </div>
  )
})
