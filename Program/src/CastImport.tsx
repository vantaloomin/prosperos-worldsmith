import { useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Undo2, Users } from 'lucide-react'
import { sendJson, type Draft, type WorldRef } from './api'
import { JobProgress } from './JobProgress'

async function castOf(file: File): Promise<unknown> {
  try {
    return JSON.parse(await file.text())
  } catch {
    throw new Error(`${file.name} is not a JSON file. Export the cast from Prospero's Dramatis as cast.json.`)
  }
}

/** A Dramatis cast file (worldsmith/cast_import.py): each side of its outer square drafted as one of the world's
 * factions, waiting for approval with the other drafts. The last approved import can be undone here. */
export function CastImport({ world, onChanged }: { world: WorldRef; onChanged: () => void }) {
  const client = useQueryClient()
  const picker = useRef<HTMLInputElement>(null)
  const key = ['cast-imports', JSON.stringify(world)]
  const imports = useQuery({ queryKey: key, queryFn: () => sendJson<{ at: string }[]>('/api/factions/imports', 'POST', world) })
  const make = useMutation({
    mutationFn: async (file: File) => sendJson<Draft>('/api/factions/import', 'POST', { ...world, cast: await castOf(file) }),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['drafts', JSON.stringify(world)] }) },
  })
  const undo = useMutation({
    mutationFn: () => sendJson('/api/factions/undo', 'POST', world),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: key }); onChanged() },
  })
  const drafted = make.data?.entries[0] as { cast: string; factions: unknown[] } | undefined
  return (
    <section className="cast-import">
      <h3>Factions</h3>
      <div className="row tight">
        <button type="button" disabled={make.isPending} onClick={() => picker.current?.click()}>
          <Users size={14} aria-hidden /> {make.isPending ? 'Drafting…' : 'Import a Dramatis cast'}
        </button>
        {!!imports.data?.length && (
          <button type="button" disabled={undo.isPending} onClick={() => undo.mutate()}><Undo2 size={14} aria-hidden /> Undo the last cast import</button>
        )}
        <input ref={picker} type="file" accept=".json,application/json" hidden aria-label="Dramatis cast file"
          onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) make.mutate(file) }} />
      </div>
      {make.isPending && <JobProgress world={world} job="cast" compact />}
      {drafted && <p className="muted small">Drafted {drafted.factions.length} factions from {drafted.cast}. Nothing is in the world until you approve them.</p>}
      {make.isError && <p className="error small" role="alert">{make.error.message}</p>}
      {undo.isError && <p className="error small" role="alert">{undo.error.message}</p>}
    </section>
  )
}
