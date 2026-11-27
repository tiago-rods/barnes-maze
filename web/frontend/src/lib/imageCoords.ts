/** Converte um clique na imagem (exibida em qualquer escala via CSS) para pixels da imagem original. */
export function toImagePixel(event: {
  clientX: number
  clientY: number
  currentTarget: HTMLImageElement
}): { x: number; y: number } {
  const img = event.currentTarget
  const rect = img.getBoundingClientRect()
  const scaleX = img.naturalWidth / rect.width
  const scaleY = img.naturalHeight / rect.height
  return {
    x: (event.clientX - rect.left) * scaleX,
    y: (event.clientY - rect.top) * scaleY,
  }
}
