import { VideoLoadStep } from '@/wizard/steps/VideoLoadStep'

export function SubmissionWizard() {
  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="mb-4 text-xl font-semibold">Wizard de submissão</h1>
      {/* Só o passo "carregar vídeo" por enquanto — os demais chegam nas próximas partes. */}
      <VideoLoadStep />
    </div>
  )
}
