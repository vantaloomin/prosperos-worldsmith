import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { sendJson, type WorldOverview, type WorldRef } from './api'
import { MapEditor } from './MapEditor'

interface InteriorItem { id: string; name: string; style: string; summary: string; rooms: number; at: { city?: string; place?: string; node?: string } }

/** A world's interiors (keeps, caves, crypts, mines): pick one to draw its rooms map, or start a new one. */
export function Interiors({ world, overview }: { world: WorldRef; overview: WorldOverview }) {
  const client = useQueryClient()
  const key = ['interiors', JSON.stringify(world)]
  const list = useQuery({ queryKey: key, queryFn: () => sendJson<{ interiors: InteriorItem[]; styles: string[] }>('/api/interiors/list', 'POST', world) })
  const [open, setOpen] = useState('')
  const [name, setName] = useState('')
  const [style, setStyle] = useState('cave')
  const [stop, setStop] = useState('')
  const make = useMutation({
    mutationFn: () => sendJson<{ id: string }>('/api/interiors/new', 'POST', { ...world, name, style, node: stop }),
    onSuccess: (made) => { void client.invalidateQueries({ queryKey: key }); setOpen(made.id); setName('') },
  })
  const chosen = list.data?.interiors.find((item) => item.id === open)
  const stopName = (item: InteriorItem) => overview.stops.find((found) => found.id === item.at.node)?.name ?? item.at.node ?? item.at.place
  return (
    <>
      <h2>Interiors</h2>
      <p className="muted small">The insides of keeps, caves, crypts and mines: rooms on levels, joined by passages. Dungeon walks a character through them room by room.</p>
      {list.isError && <p className="error">{list.error.message}</p>}
      <div className="row tight interior-list" role="group" aria-label="Interiors">
        {list.data?.interiors.map((item) => (
          <button key={item.id} type="button" aria-pressed={open === item.id} onClick={() => setOpen(open === item.id ? '' : item.id)}>
            <strong>{item.name}</strong> <span className="muted small">{item.style}, {item.rooms} room{item.rooms === 1 ? '' : 's'}{stopName(item) ? `, at ${stopName(item)}` : ''}</span>
          </button>
        ))}
        {list.data && !list.data.interiors.length && <p className="muted small">No interiors in this world yet.</p>}
      </div>
      <details className="map-text">
        <summary>New interior</summary>
        <form className="stack" onSubmit={(event) => { event.preventDefault(); if (name.trim() && stop) make.mutate() }}>
          <label className="field"><span>Name</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="The Sunken Chapel" /></label>
          <label className="field"><span>Kind</span>
            <select value={style} onChange={(event) => setStyle(event.target.value)}>{(list.data?.styles ?? []).map((item) => <option key={item}>{item}</option>)}</select>
          </label>
          <label className="field"><span>Entered from</span>
            <select value={stop} onChange={(event) => setStop(event.target.value)}>
              <option value="">A stop on the travel map…</option>
              {overview.stops.map((item) => <option key={item.id} value={item.id}>{item.name ?? item.id}</option>)}
            </select>
          </label>
          <button type="submit" disabled={!name.trim() || !stop || make.isPending}><Plus size={14} aria-hidden /> Make it</button>
          {make.isError && <p className="error">{make.error.message}</p>}
        </form>
      </details>
      {chosen && <><h3>{chosen.name}</h3>{chosen.summary && <p className="small">{chosen.summary}</p>}<MapEditor key={chosen.id} world={world} kind="interior" town={chosen.id} /></>}
    </>
  )
}
