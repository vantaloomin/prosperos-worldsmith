import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Dices, Eraser, MapPin, RotateCcw, Save, Sparkles, ZoomIn, ZoomOut } from 'lucide-react'
import { sendJson, type WorldRef } from './api'

type Cell = [number, number]
interface River { id: string; name: string; cells: Cell[]; flow?: number[] }
interface Stop { id: string; label: string; q: number; r: number; column: number; row: number; placed: boolean }
interface Site { q: number; r: number; column: number; row: number; kind: string; score: number; why: string[]; terrain: string }
interface Settings { seed: string; wind: string; rivers: string }
interface HexMap {
  key: string; exists: boolean; columns: number; rows: number; miles: number; legend: Record<string, string>
  paint: string[]; terrain: string[]; rivers: River[]; lakes: Cell[]; roads: { name: string; cells: Cell[] }[]
  stops: Stop[]; settings: Settings; can_add_towns: boolean; undo: { id: number; at: string }[]
}
interface Made { terrain: string[]; rivers: River[]; lakes: Cell[]; towns: Site[]; stops: Stop[] }

const BRUSHES: { code: string; label: string }[] = [
  { code: '~', label: 'Sea' }, { code: '.', label: 'Plains' }, { code: 'f', label: 'Forest' }, { code: 'h', label: 'Hills' },
  { code: 'm', label: 'Mountains' }, { code: 's', label: 'Marsh' }, { code: 'w', label: 'Waste' }, { code: ' ', label: 'Unpaint' },
]
const COLOURS: Record<string, string> = {
  '~': '#6f9fc8', '.': '#cfd6a0', f: '#5d8b4c', h: '#b39a68', m: '#857a70', s: '#7d9a86', w: '#dcc79c', ' ': '#e9e4d8',
}
const RIVER = '#2f6aa8'
const SQRT3 = Math.sqrt(3)

/** Axial (q, r) to the file's column and row: odd columns sit half a hex lower. */
const offsetOf = (q: number, r: number): [number, number] => [q, r + (q - (q & 1)) / 2]

function centre(size: number, column: number, row: number): [number, number] {
  return [size + column * 1.5 * size, SQRT3 * size * (row + 0.5 * (column & 1)) + (SQRT3 / 2) * size]
}

function hexAt(size: number, columns: number, rows: number, x: number, y: number): [number, number] | null {
  const guess = Math.round((x - size) / (1.5 * size))
  let best: [number, number] | null = null
  let far = Infinity
  for (let column = guess - 1; column <= guess + 1; column++) {
    if (column < 0 || column >= columns) continue
    const row0 = Math.round((y - (SQRT3 / 2) * size) / (SQRT3 * size) - 0.5 * (column & 1))
    for (let row = row0 - 1; row <= row0 + 1; row++) {
      if (row < 0 || row >= rows) continue
      const [cx, cy] = centre(size, column, row)
      const apart = (cx - x) ** 2 + (cy - y) ** 2
      if (apart < far) { far = apart; best = [column, row] }
    }
  }
  return far <= size * size ? best : null
}

/** Every hex within `radius` steps of a hex, as columns and rows. */
function around(column: number, row: number, radius: number, columns: number, rows: number): [number, number][] {
  const q0 = column
  const r0 = row - (column - (column & 1)) / 2
  const found: [number, number][] = []
  for (let dq = -radius; dq <= radius; dq++) {
    for (let dr = Math.max(-radius, -dq - radius); dr <= Math.min(radius, -dq + radius); dr++) {
      const [c, r] = offsetOf(q0 + dq, r0 + dr)
      if (c >= 0 && c < columns && r >= 0 && r < rows) found.push([c, r])
    }
  }
  return found
}

function draw(canvas: HTMLCanvasElement, size: number, map: { columns: number; rows: number }, terrain: string[], paint: string[],
  rivers: River[], roads: HexMap['roads'], stops: Stop[], sites: Site[], chosen: Site | null, showPaint: boolean) {
  const context = canvas.getContext('2d')
  if (!context) return
  context.clearRect(0, 0, canvas.width, canvas.height)
  const corners = [0, 1, 2, 3, 4, 5].map((index) => [Math.cos((Math.PI / 3) * index) * size, Math.sin((Math.PI / 3) * index) * size])
  for (let row = 0; row < map.rows; row++) {
    for (let column = 0; column < map.columns; column++) {
      const code = terrain[row]?.[column] ?? paint[row]?.[column] ?? ' '
      const [x, y] = centre(size, column, row)
      context.beginPath()
      corners.forEach(([dx, dy], index) => (index ? context.lineTo(x + dx, y + dy) : context.moveTo(x + dx, y + dy)))
      context.closePath()
      context.fillStyle = COLOURS[code] ?? COLOURS[' ']
      context.fill()
      if (size >= 6) { context.strokeStyle = 'rgba(0,0,0,0.08)'; context.lineWidth = 0.5; context.stroke() }
      if (showPaint && paint[row]?.[column] && paint[row][column] !== ' ') {
        context.fillStyle = 'rgba(35,32,27,0.55)'
        context.beginPath(); context.arc(x, y, Math.max(1, size * 0.18), 0, Math.PI * 2); context.fill()
      }
    }
  }
  context.lineCap = 'round'; context.lineJoin = 'round'
  for (const river of rivers) {
    const points = river.cells.map(([q, r]) => centre(size, ...offsetOf(q, r)))
    if (points.length < 2) continue
    // Each stretch is drawn as wide as the water it carries, curving through the midpoints between hexes.
    for (let index = 1; index < points.length; index++) {
      const flow = river.flow?.[index] ?? 0.3
      const [ax, ay] = index === 1 ? points[0] : [(points[index - 2][0] + points[index - 1][0]) / 2, (points[index - 2][1] + points[index - 1][1]) / 2]
      const [bx, by] = points[index - 1]
      const [cx, cy] = index === points.length - 1 ? points[index] : [(points[index - 1][0] + points[index][0]) / 2, (points[index - 1][1] + points[index][1]) / 2]
      context.beginPath(); context.moveTo(ax, ay); context.quadraticCurveTo(bx, by, cx, cy)
      context.strokeStyle = RIVER; context.lineWidth = Math.max(1, size * (0.12 + Math.sqrt(flow) * 0.45)); context.stroke()
    }
  }
  context.setLineDash([size * 0.5, size * 0.4])
  for (const road of roads) {
    context.beginPath()
    road.cells.forEach(([q, r], index) => { const [x, y] = centre(size, ...offsetOf(q, r)); if (index) context.lineTo(x, y); else context.moveTo(x, y) })
    context.strokeStyle = '#6b4a2f'; context.lineWidth = Math.max(1, size * 0.15); context.stroke()
  }
  context.setLineDash([])
  context.font = `${Math.max(10, Math.min(14, size * 1.2))}px system-ui, sans-serif`
  for (const site of sites) {
    const [x, y] = centre(size, site.column, site.row)
    context.beginPath(); context.arc(x, y, Math.max(4, size * 0.55), 0, Math.PI * 2)
    context.fillStyle = site === chosen ? '#d9a441' : 'rgba(255,253,248,0.85)'; context.fill()
    context.strokeStyle = '#7a3b2e'; context.lineWidth = 2; context.stroke()
  }
  for (const stop of stops) {
    const [x, y] = centre(size, stop.column, stop.row)
    context.beginPath(); context.rect(x - size * 0.45, y - size * 0.45, size * 0.9, size * 0.9)
    context.fillStyle = '#23201b'; context.fill()
    context.fillStyle = '#23201b'; context.strokeStyle = 'rgba(255,253,248,0.9)'; context.lineWidth = 3
    context.strokeText(stop.label, x + size, y + 4); context.fillText(stop.label, x + size, y + 4)
  }
}

/** The world map painter: paint sea, coast, mountains or any land on the world's hex map, and the rest of the land,
 * its rivers and lakes and good sites for towns are worked out from it (terrain.py). Saves to Dungeon's hexes file. */
export function MapPainter({ world, onTownAdded }: { world: WorldRef; onTownAdded?: () => void }) {
  const client = useQueryClient()
  const key = ['hexes', JSON.stringify(world)]
  const [size, setSize] = useState('medium')
  const read = useQuery({ queryKey: [...key, size], queryFn: () => sendJson<HexMap>('/api/hexes/read', 'POST', { ...world, size }) })
  const [paint, setPaint] = useState<string[] | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [made, setMade] = useState<Made | null>(null)
  const [brush, setBrush] = useState('~')
  const [radius, setRadius] = useState(2)
  const [zoom, setZoom] = useState(0)
  const [live, setLive] = useState(true)
  const [showPaint, setShowPaint] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [chosen, setChosen] = useState<Site | null>(null)
  const [townName, setTownName] = useState('')
  const canvas = useRef<HTMLCanvasElement>(null)
  const frame = useRef<HTMLDivElement>(null)
  const painting = useRef(false)
  const [width, setWidth] = useState(800)

  const map = read.data
  const columns = map?.columns ?? 0
  const rows = map?.rows ?? 0
  const generate = useMutation({
    mutationFn: (body: { paint: string[]; settings: Settings }) =>
      sendJson<Made>('/api/hexes/generate', 'POST', { ...world, columns, rows, paint: body.paint, ...body.settings }),
    onSuccess: (result) => { setMade(result); setChosen(null) },
  })
  useEffect(() => {
    if (!map) return
    setPaint(map.paint); setSettings(map.settings); setDirty(false); setChosen(null)
    setMade(map.terrain.length ? { terrain: map.terrain, rivers: map.rivers, lakes: map.lakes, towns: [], stops: map.stops } : null)
    // A saved map is worked out again at once, for its town sites (the same paint and seed give the same land).
    if (map.exists) generate.mutate({ paint: map.paint, settings: map.settings })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map])
  useEffect(() => {
    const element = frame.current
    if (!element) return
    const observer = new ResizeObserver(() => setWidth(element.clientWidth))
    observer.observe(element)
    return () => observer.disconnect()
  }, [map])

  const fit = columns ? Math.max(3, Math.floor((width - 8) / (1.5 * columns + 0.5))) : 6
  const hexSize = Math.max(3, Math.min(24, fit + zoom * 2))

  const save = useMutation({
    mutationFn: () => sendJson<HexMap>('/api/hexes/save', 'PUT', { ...world, columns, rows, paint, ...settings }),
    onSuccess: (saved) => client.setQueryData([...key, size], saved),
  })
  const undo = useMutation({
    mutationFn: () => sendJson<HexMap>('/api/hexes/undo', 'POST', world),
    onSuccess: (back) => client.setQueryData([...key, size], back),
  })
  const addTown = useMutation({
    mutationFn: (site: Site) => sendJson<HexMap>('/api/hexes/town', 'POST', { ...world, q: site.q, r: site.r, name: townName, summary: site.why.join('; ') + '.' }),
    onSuccess: (after) => { client.setQueryData([...key, size], after); setTownName(''); onTownAdded?.() },
  })

  const run = useCallback((nextPaint: string[], nextSettings: Settings) => generate.mutate({ paint: nextPaint, settings: nextSettings }), [generate])

  const sites = useMemo(() => made?.towns ?? [], [made])
  useEffect(() => {
    if (canvas.current && map && paint) {
      draw(canvas.current, hexSize, map, made?.terrain ?? [], paint, made?.rivers ?? [], map.roads, made?.stops ?? map.stops, sites, chosen, showPaint || !made)
    }
  }, [map, paint, made, hexSize, sites, chosen, showPaint])

  if (read.isError) return <p className="error">{read.error.message}</p>
  if (!map || !paint || !settings) return <p className="muted">Reading the map…</p>

  const pixelWidth = Math.ceil(hexSize * (1.5 * columns + 0.5))
  const pixelHeight = Math.ceil(SQRT3 * hexSize * (rows + 0.5))

  const stroke = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    const at = hexAt(hexSize, columns, rows, event.clientX - box.left, event.clientY - box.top)
    if (!at) return
    const lines = paint.map((line) => line.split(''))
    let changed = false
    for (const [column, row] of around(at[0], at[1], radius - 1, columns, rows)) {
      if (lines[row][column] !== brush) { lines[row][column] = brush; changed = true }
    }
    if (changed) { setPaint(lines.map((line) => line.join(''))); setDirty(true) }
  }
  const pick = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    const at = hexAt(hexSize, columns, rows, event.clientX - box.left, event.clientY - box.top)
    const site = at && sites.find((item) => Math.abs(item.column - at[0]) + Math.abs(item.row - at[1]) <= 1)
    if (site) { setChosen(site); return true }
    return false
  }
  const change = (next: Partial<Settings>) => {
    const merged = { ...settings, ...next }
    setSettings(merged); setDirty(true)
    if (live) run(paint, merged)
  }
  const clear = () => {
    const blank = paint.map((line) => ' '.repeat(line.length))
    setPaint(blank); setDirty(true)
    if (live) run(blank, settings)
  }

  return (
    <div className="painter">
      <p className="muted small">
        Paint the sea, a coast, a mountain range or any land, and the rest follows: land rises from the coast and around
        your mountains, the wind brings rain off the sea and leaves a rain shadow behind the ranges, water runs downhill
        into rivers that join and reach the sea, basins fill into lakes, and the best places for towns are marked.
        Leave it all unpainted for a whole continent from the seed.
      </p>
      <div className="row tight painter-tools" role="group" aria-label="Brush">
        {BRUSHES.map((item) => (
          <button key={item.code} type="button" aria-pressed={brush === item.code} onClick={() => setBrush(item.code)} title={item.label}>
            <span className="swatch" style={{ background: COLOURS[item.code] }} aria-hidden />{item.code === ' ' ? <Eraser size={13} aria-hidden /> : null} {item.label}
          </button>
        ))}
        <label className="inline">Brush <input type="range" min={1} max={8} value={radius} onChange={(event) => setRadius(Number(event.target.value))} aria-label="Brush size" /> {radius}</label>
      </div>
      <div className="row tight painter-tools">
        <label className="inline">Wind from <select value={settings.wind} onChange={(event) => change({ wind: event.target.value })}>
          {['west', 'east', 'north', 'south'].map((item) => <option key={item}>{item}</option>)}</select></label>
        <label className="inline">Rivers <select value={settings.rivers} onChange={(event) => change({ rivers: event.target.value })}>
          {['few', 'some', 'many'].map((item) => <option key={item}>{item}</option>)}</select></label>
        <label className="inline">Seed <input value={settings.seed} onChange={(event) => setSettings({ ...settings, seed: event.target.value })} onBlur={() => change({})} size={12} /></label>
        <button type="button" onClick={() => change({ seed: Math.random().toString(36).slice(2, 8) })}><Dices size={14} aria-hidden /> New seed</button>
        <button type="button" onClick={clear}><Eraser size={14} aria-hidden /> Clear paint</button>
        {!map.exists && <label className="inline">Size <select value={size} onChange={(event) => setSize(event.target.value)}>
          {['small', 'medium', 'large'].map((item) => <option key={item}>{item}</option>)}</select></label>}
      </div>
      <div className="row tight painter-tools">
        <label className="inline"><input type="checkbox" checked={live} onChange={(event) => setLive(event.target.checked)} /> Work it out after each stroke</label>
        <label className="inline"><input type="checkbox" checked={showPaint} onChange={(event) => setShowPaint(event.target.checked)} /> Mark my paint</label>
        <button type="button" onClick={() => run(paint, settings)} disabled={generate.isPending}><Sparkles size={14} aria-hidden /> {generate.isPending ? 'Working…' : 'Generate'}</button>
        <button type="button" onClick={() => setZoom(zoom - 1)} aria-label="Zoom out" disabled={hexSize <= 3}><ZoomOut size={14} /></button>
        <button type="button" onClick={() => setZoom(zoom + 1)} aria-label="Zoom in" disabled={hexSize >= 24}><ZoomIn size={14} /></button>
        <span className="spacer" />
        <button type="button" onClick={() => save.mutate()} disabled={save.isPending || (!dirty && map.exists)}><Save size={14} aria-hidden /> {save.isPending ? 'Saving…' : 'Save to the world'}</button>
        <button type="button" onClick={() => undo.mutate()} disabled={!map.undo.length || undo.isPending}><RotateCcw size={14} aria-hidden /> Undo last save</button>
      </div>
      {[generate, save, undo, addTown].map((job, index) => job.isError && <p key={index} className="error">{job.error.message}</p>)}
      <div className="painter-frame" ref={frame}>
        <canvas ref={canvas} width={pixelWidth} height={pixelHeight} aria-label="World map: drag to paint"
          onPointerDown={(event) => { if (pick(event)) return; painting.current = true; event.currentTarget.setPointerCapture(event.pointerId); stroke(event) }}
          onPointerMove={(event) => { if (painting.current) stroke(event) }}
          onPointerUp={() => { if (painting.current && live) run(paint, settings); painting.current = false }} />
      </div>
      <p className="muted small">
        {columns} by {rows} hexes of {map.miles} miles. {made ? `${made.rivers.length} rivers, ${made.lakes.length} lake hexes.` : 'Not worked out yet.'}
        {dirty ? ' Not saved yet.' : map.exists ? ' Saved.' : ''} Dungeon's hex crawl uses the rivers: crossing one off the road takes time, and a road over one is a bridge or a ford.
      </p>
      <h3><MapPin size={14} aria-hidden /> Suggested town sites</h3>
      {!sites.length && <p className="muted small">Generate the map to see where towns would grow.</p>}
      <ol className="sites">
        {sites.map((site) => (
          <li key={`${site.q},${site.r}`}>
            <button type="button" className="link" aria-pressed={site === chosen} onClick={() => setChosen(site === chosen ? null : site)}>
              {site.kind}</button> <span className="small">on {site.terrain}: {site.why.join('; ')}</span>
            {site === chosen && (
              <form className="row tight" onSubmit={(event) => { event.preventDefault(); if (townName.trim()) addTown.mutate(site) }}>
                {!map.can_add_towns ? <span className="muted small">This world has no Road city for new stops; make the town with New town.</span>
                  : dirty || !map.exists ? <span className="muted small">Save the map first, then make this site a town.</span>
                    : <><input value={townName} onChange={(event) => setTownName(event.target.value)} placeholder="Town name" aria-label="Town name" />
                      <button type="submit" disabled={!townName.trim() || addTown.isPending}><MapPin size={14} aria-hidden /> Make it a town</button></>}
              </form>
            )}
          </li>
        ))}
      </ol>
      {map.can_add_towns && <p className="muted small">A town made here is a stop on the travel map, waiting in Towns to build until the town wizard builds it out.</p>}
    </div>
  )
}
