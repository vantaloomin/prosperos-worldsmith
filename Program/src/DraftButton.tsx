import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'
import { sendJson, type Draft, type WorldRef } from './api'
import { JobProgress } from './JobProgress'

/** "Draft with AI" for one list of a town: an optional ask, then a draft lands in the queue for approval. */
export function DraftButton({ world, town, target, what }: { world: WorldRef; town: string; target: string; what: string }) {
  const client = useQueryClient()
  const [ask, setAsk] = useState('')
  const make = useMutation({
    mutationFn: () => sendJson<Draft>('/api/drafts', 'POST', { ...world, town, target, ask }),
    onSuccess: async () => { setAsk(''); await client.invalidateQueries({ queryKey: ['drafts', JSON.stringify(world)] }) },
  })
  return (
    <div className="draft-ask">
      <form onSubmit={(event) => { event.preventDefault(); make.mutate() }}>
        <input aria-label={`What ${what} to draft`} placeholder={`Ask for ${what}, e.g. "a smugglers' den by the river"`}
          value={ask} onChange={(event) => setAsk(event.target.value)} disabled={make.isPending} />
        <button type="submit" disabled={make.isPending}><Sparkles size={14} aria-hidden /> {make.isPending ? 'Drafting…' : 'Draft with AI'}</button>
      </form>
      {make.isPending && <JobProgress world={world} job="draft" compact />}
      {make.isSuccess && <p className="muted small">Drafted. Review it in the queue on the right.</p>}
      {make.isError && <p className="error small">{make.error.message}</p>}
    </div>
  )
}
