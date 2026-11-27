interface FieldHintProps {
  text: string
}

/** Bolinha "i" com dica ao passar o mouse, para explicar o que um campo espera. */
export function FieldHint({ text }: FieldHintProps) {
  return (
    <span
      title={text}
      className="inline-flex h-4 w-4 shrink-0 cursor-help items-center justify-center rounded-full border border-zinc-300 text-[10px] font-semibold text-zinc-500"
    >
      i
    </span>
  )
}
