import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'
import { sendJson, type Draft, type WorldOverview, type WorldRef } from './api'

/** The new town wizard: a pitch and where the town sits; the whole town is drafted for approval. */
export function NewTown({ world, overview }: { world: WorldRef; overview: WorldOverview }) {
  const client = useQueryClient()
  const real = overview.towns.filter((town) => !town.road)
  const roadside = overview.stops.filter((stop) => stop.road)
  const [form, setForm] = useState({ pitch: '', name: '', how: 'new', near: real[0]?.id ?? '', replaces: roadside[0]?.id ?? '', hours: 6, terrain: 'the road', danger: 'low' })
  const set = (patch: Partial<typeof form>) => setForm((current) => ({ ...current, ...patch }))
  const make = useMutation({
    mutationFn: () => sendJson<Draft>('/api/towns/new', 'POST', {
      ...world, pitch: form.pitch, name: form.name, near: form.how === 'new' ? form.near : null,
      replaces: form.how === 'grow' ? form.replaces : null, hours: form.hours, terrain: form.terrain, danger: form.danger,
    }),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['drafts', JSON.stringify(world)] }) },
  })
  return (
    <form className="record new-town" onSubmit={(event) => { event.preventDefault(); make.mutate() }}>
      <h2>New town</h2>
      <p className="muted">Pitch the town and the model drafts all of it: neighborhoods, places, people, employers, prices,
        customs, events and climate. Shared settings such as money, era and name banks come from {overview.world.name}'s other towns. Nothing is written until you approve it.</p>
      <div className="field">
        <span>Pitch <b>*</b></span>
        <textarea aria-label="Pitch" rows={5} value={form.pitch} placeholder="What it is, who runs it, what is rotten there."
          onChange={(event) => set({ pitch: event.target.value })} />
      </div>
      <div className="field"><span>Name (optional)</span><input aria-label="Name" value={form.name} onChange={(event) => set({ name: event.target.value })} /></div>
      {overview.stops.length > 0 && (
        <fieldset className="field">
          <legend>On the travel map</legend>
          <label><input type="radio" checked={form.how === 'new'} onChange={() => set({ how: 'new' })} /> A new stop, by road from</label>
          {form.how === 'new' && (
            <div className="row">
              <select aria-label="Near" value={form.near} onChange={(event) => set({ near: event.target.value })}>
                {real.map((town) => <option key={town.id} value={town.id}>{town.name}</option>)}
              </select>
              <label className="small-field"><span>Hours away</span><input aria-label="Hours" type="number" min={0.1} step="any" value={form.hours} onChange={(event) => set({ hours: Number(event.target.value) })} /></label>
              <label className="small-field"><span>Over</span><input aria-label="Terrain" value={form.terrain} onChange={(event) => set({ terrain: event.target.value })} /></label>
              <select aria-label="Danger" value={form.danger} onChange={(event) => set({ danger: event.target.value })}>
                {['none', 'low', 'medium', 'high'].map((level) => <option key={level} value={level}>{level} danger</option>)}
              </select>
            </div>
          )}
          {roadside.length > 0 && <label><input type="radio" checked={form.how === 'grow'} onChange={() => set({ how: 'grow' })} /> Grow a roadside stop into this town</label>}
          {form.how === 'grow' && (
            <select aria-label="Roadside stop" value={form.replaces} onChange={(event) => set({ replaces: event.target.value })}>
              {roadside.map((stop) => <option key={stop.id} value={stop.id}>{stop.name ?? stop.id}</option>)}
            </select>
          )}
        </fieldset>
      )}
      <div className="row">
        <button type="submit" disabled={make.isPending || !form.pitch.trim()}><Sparkles size={14} aria-hidden /> {make.isPending ? 'Drafting the town… (a minute or two)' : 'Draft the town'}</button>
      </div>
      {make.isSuccess && <p className="note">Drafted {make.data.entries[0]?.name as string}. Review it in the queue on the right, then approve to add it.</p>}
      {make.isError && <p className="error">{make.error.message}</p>}
    </form>
  )
}
