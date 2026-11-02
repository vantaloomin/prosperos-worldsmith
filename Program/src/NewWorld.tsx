import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Hammer, Plus, Sparkles } from 'lucide-react'
import { sendJson, type Draft, type WorldOverview, type WorldRef } from './api'

interface TownStop { id: string; name: string; pitch: string }
interface DraftProgress {
  running: boolean; step?: string; index?: number; of?: number; label?: string; attempt?: number
  started?: string; step_started?: string; problems?: string[]
}

function since(start: string | undefined, now: number): string {
  if (!start) return ''
  const seconds = Math.max(0, Math.round((now - Date.parse(start)) / 1000))
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s`
}

/** While a world is drafted: the step it is on out of all of them, which try at it, and how long it has taken. */
function DraftSteps({ world }: { world: WorldRef }) {
  const progress = useQuery({
    queryKey: ['draft-progress', JSON.stringify(world)], refetchInterval: 1500,
    queryFn: () => sendJson<DraftProgress>('/api/worlds/draft/progress', 'POST', world),
  })
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer) }, [])
  const step = progress.data
  if (!step?.running || !step.index || !step.of) return <p className="muted small" role="status">Starting…</p>
  return (
    <div className="draft-steps" role="status" aria-live="polite">
      <div className="draft-bar" role="progressbar" aria-valuemin={0} aria-valuemax={step.of} aria-valuenow={step.index - 1}
        aria-label="Drafting the world">
        <span style={{ width: `${((step.index - 0.5) / step.of) * 100}%` }} />
      </div>
      <p className="small">
        Step {step.index} of {step.of}: {step.label}{step.attempt && step.attempt > 1 ? ' (second try)' : ''}…
        <span className="muted"> {since(step.step_started, now)} on this step, {since(step.started, now)} in all.</span>
      </p>
      {step.attempt && step.attempt > 1 && !!step.problems?.length &&
        <p className="muted small">The first try was sent back: {step.problems.join('; ')}</p>}
      <p className="muted small">Each step is one call to the model and can take a minute or two. The timer keeps counting while it works.</p>
    </div>
  )
}

/** Starting a world of one's own: a name and a pitch make its folder, and the wizard drafts the rest. */
export function NewWorldForm({ onMade, busy }: { onMade: (folder: string) => void; busy: boolean }) {
  const [form, setForm] = useState({ name: '', pitch: '', parent: '' })
  const make = useMutation({
    mutationFn: () => sendJson<{ folder: string }>('/api/worlds/new', 'POST', { name: form.name, pitch: form.pitch, parent: form.parent.trim() || null }),
    onSuccess: (made) => onMade(made.folder),
  })
  return (
    <section>
      <h3>New world</h3>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); make.mutate() }}>
        <input aria-label="New world name" placeholder="Name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
        <textarea aria-label="New world pitch" rows={3} placeholder="Pitch: what the world is, who holds power, what is going wrong."
          value={form.pitch} onChange={(event) => setForm({ ...form, pitch: event.target.value })} />
        <input aria-label="New world parent folder" placeholder="Folder to make it in (optional)" value={form.parent}
          onChange={(event) => setForm({ ...form, parent: event.target.value })} />
        <button type="submit" disabled={busy || make.isPending || !form.name.trim()}><Plus size={14} aria-hidden /> Make the world</button>
      </form>
      {make.isError && <p className="error">{make.error.message}</p>}
    </section>
  )
}

/** The new world wizard on a world of one's own: draft the whole world from its pitch, then grow its towns. */
export function WorldWizard({ world, overview }: { world: WorldRef; overview: WorldOverview }) {
  const client = useQueryClient()
  const drafted = overview.stops.length > 0
  const [pitch, setPitch] = useState(overview.world.pitch ?? '')
  const [size, setSize] = useState('medium')
  const draft = useMutation({
    mutationFn: () => sendJson<Draft>('/api/worlds/draft', 'POST', { ...world, pitch, size }),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['drafts', JSON.stringify(world)] }) },
  })
  if (overview.kind !== 'folder') return null
  if (drafted) return <TownStops world={world} />
  return (
    <form className="record wizard" onSubmit={(event) => { event.preventDefault(); draft.mutate() }}>
      <h3><Sparkles size={15} aria-hidden /> Draft the whole world</h3>
      <p className="muted small">The model writes the world in four parts: its outline (regions, towns and other stops, the roads
        between them), its people (names, careers, prices, climate), its factions and their jobs, and its story (arcs, road
        and camp encounters, wild sites, hidden truths and lore). It all comes back as one draft to approve. Then each town
        is drafted on its own.</p>
      <div className="field">
        <span>Pitch <b>*</b></span>
        <textarea aria-label="World pitch" rows={5} value={pitch} onChange={(event) => setPitch(event.target.value)} />
      </div>
      <div className="row">
        <select aria-label="World size" value={size} onChange={(event) => setSize(event.target.value)}>
          <option value="small">Small (3 to 5 towns)</option>
          <option value="medium">Medium (5 to 8 towns)</option>
          <option value="large">Large (8 to 12 towns)</option>
        </select>
        <button type="submit" disabled={draft.isPending || !pitch.trim()}>
          <Sparkles size={14} aria-hidden /> {draft.isPending ? 'Drafting the world…' : 'Draft the world'}
        </button>
      </div>
      {draft.isPending && <DraftSteps world={world} />}
      {draft.isSuccess && <p className="note">Drafted {String(draft.data.entries[0]?.name)}. Review it in the queue on the right, then approve it.</p>}
      {draft.isError && <p className="error">{draft.error.message}</p>}
    </form>
  )
}

/** The world's town stops still on the Road, each grown into a whole town by the town wizard. */
function TownStops({ world }: { world: WorldRef }) {
  const client = useQueryClient()
  const key = ['town-stops', JSON.stringify(world)]
  const stops = useQuery({ queryKey: key, queryFn: () => sendJson<TownStop[]>('/api/worlds/town-stops', 'POST', world) })
  const pending = useQuery({ queryKey: ['drafts', JSON.stringify(world)], queryFn: () => sendJson<Draft[]>('/api/drafts/pending', 'POST', world) })
  const [working, setWorking] = useState<string[]>([])
  const grow = useMutation({
    mutationFn: async (chosen: TownStop[]) => {
      for (const stop of chosen) {
        setWorking((now) => [...now, stop.id])
        try {
          await sendJson<Draft>('/api/towns/new', 'POST', { ...world, pitch: stop.pitch, name: stop.name, replaces: stop.id })
          await client.invalidateQueries({ queryKey: ['drafts', JSON.stringify(world)] })
        } finally {
          setWorking((now) => now.filter((id) => id !== stop.id))
        }
      }
    },
  })
  const queued = new Set((pending.data ?? []).filter((item) => item.target === 'town').map((item) => item.town))
  const left = (stops.data ?? []).filter((stop) => !queued.has(stop.id))
  if (!stops.data?.length) return null
  return (
    <section className="record wizard">
      <h3><Hammer size={15} aria-hidden /> Towns to build</h3>
      <p className="muted small">These towns are still stops on the Road. Draft each one into a whole town: it keeps the stop's
        place on the map and takes the world's money, names and careers.</p>
      <ul className="choices">
        {stops.data.map((stop) => (
          <li key={stop.id} className="row">
            <span><strong>{stop.name}</strong> <span className="muted small">{stop.pitch}</span></span>
            {queued.has(stop.id) ? <span className="muted small">waiting for approval</span> : (
              <button type="button" disabled={grow.isPending} onClick={() => grow.mutate([stop])}>
                {working.includes(stop.id) ? 'Drafting…' : 'Draft'}
              </button>
            )}
          </li>
        ))}
      </ul>
      {left.length > 1 && <button type="button" disabled={grow.isPending} onClick={() => grow.mutate(left)}>
        <Sparkles size={14} aria-hidden /> {grow.isPending ? 'Drafting the towns one by one…' : `Draft all ${left.length}`}</button>}
      {grow.isError && <p className="error">{grow.error.message}</p>}
    </section>
  )
}
