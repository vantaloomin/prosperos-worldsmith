import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, EyeOff, X } from 'lucide-react'
import { sendJson, type Draft, type WorldRef } from './api'

const label = (entry: Record<string, unknown>) => String(entry.name ?? entry.title ?? entry.item ?? entry.id ?? 'Entry')
const about = (entry: Record<string, unknown>) => String(entry.summary ?? entry.about ?? entry.hook ?? '')

/** Drafts waiting for the author: what the model proposed, approved into the town or thrown away. */
export function DraftsPane({ world }: { world: WorldRef }) {
  const client = useQueryClient()
  const key = ['drafts', JSON.stringify(world)]
  const pending = useQuery({ queryKey: key, queryFn: () => sendJson<Draft[]>('/api/drafts/pending', 'POST', world) })
  const decide = useMutation({
    mutationFn: ({ id, approve }: { id: number; approve: boolean }) => sendJson(`/api/drafts/${id}/decide`, 'POST', { ...world, approve }),
    onSettled: async () => {
      await client.invalidateQueries({ queryKey: key })
      await client.invalidateQueries({ queryKey: ['town'] })
    },
  })
  if (!pending.data?.length) return <p className="muted small">No drafts waiting. Use "Draft with AI" on a town's tab to ask for some.</p>
  return (
    <div className="drafts">
      {decide.isError && <p className="error small" role="alert">{decide.error.message}</p>}
      {pending.data.map((draft) => (
        <article key={draft.id} className="draft">
          <header>
            <strong>{draft.entries.length} new {draft.target.replace(/_/g, ' ')}</strong>
            <span className="muted small"> for {draft.town}</span>
          </header>
          {draft.ask && <p className="muted small">“{draft.ask}”</p>}
          {draft.hidden > 0 && <p className="hidden-note small"><EyeOff size={13} aria-hidden /> {draft.hidden} hold a hidden truth</p>}
          <ul>
            {draft.entries.map((entry, at) => (
              <li key={at}><strong>{label(entry)}</strong>{about(entry) && <span className="muted"> · {about(entry)}</span>}</li>
            ))}
          </ul>
          <details className="small"><summary>Exact JSON</summary><pre>{JSON.stringify(draft.entries, null, 2)}</pre></details>
          <div className="row">
            <button type="button" disabled={decide.isPending} onClick={() => decide.mutate({ id: draft.id, approve: true })}><Check size={14} aria-hidden /> Approve</button>
            <button type="button" disabled={decide.isPending} onClick={() => decide.mutate({ id: draft.id, approve: false })}><X size={14} aria-hidden /> Reject</button>
          </div>
        </article>
      ))}
    </div>
  )
}
