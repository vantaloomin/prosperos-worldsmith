import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, EyeOff, X } from 'lucide-react'
import { sendJson, type Draft, type WorldRef } from './api'

const label = (entry: Record<string, unknown>) => String(entry.name ?? entry.title ?? entry.item ?? entry.id ?? 'Entry')
const about = (entry: Record<string, unknown>) => String(entry.summary ?? entry.about ?? entry.hook ?? '')

function WorldSummary({ world }: { world: Record<string, unknown> }) {
  const towns = (world.towns as string[]) ?? []
  return (
    <p className="small"><strong>{label(world)}</strong> · {String(world.genre ?? '')}<br />
      {about(world)}<br />
      <span className="muted">{String(world.regions)} regions, {String(world.stops)} stops, {String(world.factions)} factions,
        {' '}{String(world.arcs)} arcs, {String(world.careers)} careers. Towns to build: {towns.join(', ')}</span></p>
  )
}

interface CastFactions { cast: string; factions: { id: string; name: string; summary: string; holds: string[]; jobs: unknown[] }[] }

function FactionsSummary({ entry }: { entry: CastFactions }) {
  return (
    <ul>
      {entry.factions.map((faction) => (
        <li key={faction.id}><strong>{faction.name}</strong><span className="muted"> · {faction.summary}<br />
          {faction.holds.length ? `holds ${faction.holds.join(', ')}` : 'holds no stop'}, {faction.jobs.length} job{faction.jobs.length === 1 ? '' : 's'}</span></li>
      ))}
    </ul>
  )
}

const heading = (draft: Draft) => draft.target === 'world' ? 'The whole world' : draft.target === 'town' ? 'A new town'
  : draft.target === 'factions' ? `${(draft.entries[0] as unknown as CastFactions).factions.length} factions from ${String(draft.entries[0].cast)}`
  : `${draft.entries.length} new ${draft.target.replace(/_/g, ' ')}`
const exact = (draft: Draft) => draft.target === 'world' ? draft.entries[0].files : draft.target === 'factions' ? draft.entries[0].factions : draft.entries
// Approving these changes the world itself, not one town's lists.
const WHOLE_WORLD = ['town', 'world', 'factions']

/** Drafts waiting for the author: what the model proposed, approved into the town or thrown away. */
export function DraftsPane({ world, onWorldChanged }: { world: WorldRef; onWorldChanged: () => void }) {
  const client = useQueryClient()
  const key = ['drafts', JSON.stringify(world)]
  const pending = useQuery({ queryKey: key, queryFn: () => sendJson<Draft[]>('/api/drafts/pending', 'POST', world) })
  const decide = useMutation({
    mutationFn: ({ id, approve }: { id: number; approve: boolean }) => sendJson(`/api/drafts/${id}/decide`, 'POST', { ...world, approve }),
    onSuccess: (_, decided) => {
      const item = pending.data?.find((draft) => draft.id === decided.id)
      if (decided.approve && item && WHOLE_WORLD.includes(item.target)) onWorldChanged()
    },
    onSettled: async () => {
      await client.invalidateQueries({ queryKey: key })
      await client.invalidateQueries({ queryKey: ['town'] })
      await client.invalidateQueries({ queryKey: ['town-stops'] })
      await client.invalidateQueries({ queryKey: ['cast-imports'] })
    },
  })
  if (!pending.data?.length) return <p className="muted small">No drafts waiting. Use "Draft with AI" on a town's tab to ask for some.</p>
  return (
    <div className="drafts">
      {decide.isError && <p className="error small" role="alert">{decide.error.message}</p>}
      {pending.data.map((draft) => (
        <article key={draft.id} className="draft">
          <header>
            <strong>{heading(draft)}</strong>
            <span className="muted small"> for {draft.town}</span>
          </header>
          {draft.ask && <p className="muted small">“{draft.ask}”</p>}
          {draft.hidden > 0 && <p className="hidden-note small"><EyeOff size={13} aria-hidden /> {draft.hidden} hold a hidden truth</p>}
          {draft.target === 'world' ? <WorldSummary world={draft.entries[0]} /> : draft.target === 'factions' ? <FactionsSummary entry={draft.entries[0] as unknown as CastFactions} /> : draft.target === 'town' ? (
            <p className="small"><strong>{label(draft.entries[0])}</strong> · {about(draft.entries[0])}<br />
              <span className="muted">{(['neighborhoods', 'places', 'notables', 'employers'] as const)
                .map((key) => `${((draft.entries[0][key] as unknown[]) ?? []).length} ${key}`).join(', ')}</span></p>
          ) : <ul>
            {draft.entries.map((entry, at) => (
              <li key={at}><strong>{label(entry)}</strong>{about(entry) && <span className="muted"> · {about(entry)}</span>}</li>
            ))}
          </ul>}
          <details className="small"><summary>Exact JSON</summary><pre>{JSON.stringify(exact(draft), null, 2)}</pre></details>
          <div className="row">
            <button type="button" disabled={decide.isPending} onClick={() => decide.mutate({ id: draft.id, approve: true })}><Check size={14} aria-hidden /> Approve</button>
            <button type="button" disabled={decide.isPending} onClick={() => decide.mutate({ id: draft.id, approve: false })}><X size={14} aria-hidden /> Reject</button>
          </div>
        </article>
      ))}
    </div>
  )
}
