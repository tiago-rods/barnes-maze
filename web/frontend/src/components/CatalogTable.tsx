import { useEffect, useState } from 'react'

import { type CatalogEntry, listCatalog } from '@/api/catalog'

interface CatalogTableProps {
  experimentId?: number
}

export function CatalogTable({ experimentId }: CatalogTableProps) {
  const [rows, setRows] = useState<CatalogEntry[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listCatalog(experimentId)
      .then(setRows)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [experimentId])

  if (error) return <p className="text-sm text-red-600">{error}</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-200 text-zinc-500">
            <th className="py-1 pr-3">Trial</th>
            <th className="py-1 pr-3">Animal</th>
            <th className="py-1 pr-3">Sessão</th>
            <th className="py-1 pr-3">Fase</th>
            <th className="py-1 pr-3">Situação</th>
            <th className="py-1 pr-3">Cobertura pose</th>
            <th className="py-1 pr-3">Qualidade pose</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.trial_id} className="border-b border-zinc-100">
              <td className="py-1 pr-3">#{row.trial_id}</td>
              <td className="py-1 pr-3">{row.animal ?? '-'}</td>
              <td className="py-1 pr-3">{row.sessao}</td>
              <td className="py-1 pr-3">{row.fase}</td>
              <td className="py-1 pr-3">{row.situacao}</td>
              <td className="py-1 pr-3">
                {row.cobertura_pose !== null ? `${(row.cobertura_pose * 100).toFixed(0)}%` : '-'}
              </td>
              <td className="py-1 pr-3">{row.qualidade_pose ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <p className="py-2 text-sm text-zinc-500">Nenhum trial.</p>}
    </div>
  )
}
