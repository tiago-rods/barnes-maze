import { Label } from '@/components/ui/label'
import { FieldHint } from '@/components/ui/field-hint'

interface FieldLabelProps {
  htmlFor: string
  text: string
  hint: string
}

/** `<Label>` + bolinha "i" com dica, para usar em qualquer campo do wizard. */
export function FieldLabel({ htmlFor, text, hint }: FieldLabelProps) {
  return (
    <div className="flex items-center gap-1">
      <Label htmlFor={htmlFor}>{text}</Label>
      <FieldHint text={hint} />
    </div>
  )
}
