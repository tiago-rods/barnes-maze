import { useEffect, useState } from 'react'

import { type ExperimentSummary, listExperiments } from '@/api/experiments'
import { downloadUrl, exportProbes, exportTrials } from '@/api/report'
import { CatalogTable } from '@/components/CatalogTable'
import { JobHistoryTable } from '@/components/JobHistoryTable'
import { LearningCurveChart } from '@/components/LearningCurveChart'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'

export function Dashboard() {
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([])
  const [experimentId, setExperimentId] = useState<number | null>(null)
  const [exportMessage, setExportMessage] = useState<string | null>(null)
  const [downloadLink, setDownloadLink] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listExperiments()
      .then(setExperiments)
      .catch(() => {})
  }, [])

  async function handleExportTrials() {
    setError(null)
    if (experimentId === null) return
    try {
      const result = await exportTrials({ experiment_id: experimentId })
      setExportMessage(
        `trials.csv: ${result.count} trial(s), ${result.pendencias.length} pendência(s).`,
      )
      setDownloadLink(downloadUrl(result.path))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleExportProbes() {
    setError(null)
    if (experimentId === null) return
    try {
      const result = await exportProbes({ experiment_id: experimentId })
      setExportMessage(
        `probes.csv: ${result.count} probe(s), ${result.pendencias.length} pendência(s).`,
      )
      setDownloadLink(downloadUrl(result.path))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="mb-4 text-xl font-semibold">Dashboard</h1>

      <Card className="mb-4">
        <CardHeader>
          <CardTitle>Experimento</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-1">
          <Label htmlFor="dashboard-experiment">Experimento</Label>
          <select
            id="dashboard-experiment"
            className="h-9 w-64 rounded-md border border-zinc-200 bg-white px-3 text-sm"
            value={experimentId ?? ''}
            onChange={(e) => setExperimentId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">Todos</option>
            {experiments.map((exp) => (
              <option key={exp.id} value={exp.id}>
                #{exp.id} — {exp.name}
              </option>
            ))}
          </select>
        </CardContent>
      </Card>

      <Card className="mb-4">
        <CardHeader>
          <CardTitle>Catálogo de trials</CardTitle>
        </CardHeader>
        <CardContent>
          <CatalogTable experimentId={experimentId ?? undefined} />
        </CardContent>
      </Card>

      <Card className="mb-4">
        <CardHeader>
          <CardTitle>Curvas de aprendizado</CardTitle>
        </CardHeader>
        <CardContent>
          <LearningCurveChart experimentId={experimentId ?? undefined} />
        </CardContent>
      </Card>

      <Card className="mb-4">
        <CardHeader>
          <CardTitle>Exportar (US-25/26)</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex gap-2">
            <Button onClick={handleExportTrials} disabled={experimentId === null}>
              Exportar trials.csv
            </Button>
            <Button onClick={handleExportProbes} disabled={experimentId === null}>
              Exportar probes.csv
            </Button>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          {exportMessage && <p className="text-sm text-zinc-600">{exportMessage}</p>}
          {downloadLink && (
            <a href={downloadLink} className="text-sm text-blue-600 underline" download>
              Baixar arquivo
            </a>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Jobs recentes</CardTitle>
        </CardHeader>
        <CardContent>
          <JobHistoryTable />
        </CardContent>
      </Card>
    </div>
  )
}
