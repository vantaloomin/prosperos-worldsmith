import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Undo2, Users } from 'lucide-react'
import { sendJson, type Draft, type Town, type WorldRef } from './api'
import { JobProgress } from './JobProgress'

async function castOf(file: File): Promise<unknown> {
  try {
    return JSON.parse(await file.text())
  } catch {
    throw new Error(`${file.name} is not a JSON file. Export the cast from Prospero's Dramatis as cast.json.`)
  }
}

type CastDraft = Draft & { people?: Draft | null; people_problem?: string }

/** A Dramatis cast file (worldsmith/cast_import.py): each side of its outer square drafted as one of the world's
 * factions, and with a town picked, its people as that town's notables; both wait for approval with the other drafts.
 * The last approved import can be undone here. */
export function CastImport({ world, towns, onChanged }: { world: WorldRef; towns: Town[]; onChanged: () => void }) {
  const client = useQueryClient()
  const picker = useRef<HTMLInputElement>(null)
  const homes = towns.filter((item) => !item.road)
  const [town, setTown] = useState('')
  const key = ['cast-imports', JSON.stringify(world)]
  const imports = useQuery({ queryKey: key, queryFn: () => sendJson<{ at: string }[]>('/api/factions/imports', 'POST', world) })
  const make = useMutation({
    mutationFn: async (file: File) => sendJson<CastDraft>('/api/factions/import', 'POST', { ...world, cast: await castOf(file), town }),
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
        {homes.length > 0 && (
          <select aria-label="Where its people live" value={town} disabled={make.isPending} onChange={(event) => setTown(event.target.value)}>
            <option value="">Sides only</option>
            {homes.map((item) => <option key={item.id} value={item.id}>People in {item.name}</option>)}
          </select>
        )}
        <input ref={picker} type="file" accept=".json,application/json" hidden aria-label="Dramatis cast file"
          onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) make.mutate(file) }} />
      </div>
      {make.isPending && <JobProgress world={world} job="cast" compact />}
      {drafted && <p className="muted small">Drafted {drafted.factions.length} factions from {drafted.cast}{peopleLine(make.data)}. Nothing is in the world until you approve them.</p>}
      {make.data?.people_problem && <p className="error small" role="alert">Its people were not drafted: {make.data.people_problem}</p>}
      {make.isError && <p className="error small" role="alert">{make.error.message}</p>}
      {undo.isError && <p className="error small" role="alert">{undo.error.message}</p>}
    </section>
  )
}

function peopleLine(draft: CastDraft | undefined): string {
  const count = draft?.people?.entries.length ?? 0
  return count ? `, and ${count} ${count === 1 ? 'person' : 'people'} as notables` : ''
}
