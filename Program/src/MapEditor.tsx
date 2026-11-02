import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Link2, MousePointer2, Plus, Save, Trash2, Undo2, ZoomIn, ZoomOut } from 'lucide-react'
import { sendJson, type WorldRef } from './api'

export interface MapNode { id: string; label: string; group: string | null; kind?: string; type?: string; x?: number; y?: number; placed?: boolean; safe?: boolean }
export interface MapGroup { id: string; label: string; x?: number; y?: number }
export interface MapLink { from: string; to: string; label: string }
export interface MapGraph {
  map: 'travel' | 'town'; town?: string; nodes: MapNode[]; groups: MapGroup[]; links: MapLink[]
  regions?: { id: string; label: string }[]; addable?: { id: string; label: string; kind: string }[]; kinds?: string[]
  mermaid?: string; undo?: { at: string }[]
}
type Picked = { type: 'node' | 'group'; id: string } | { type: 'link'; index: number } | null
type Drag = { type: 'node' | 'group' | 'pan'; id?: string; dx: number; dy: number; moved: boolean; from?: { x: number; y: number } } | null

const COLORS = ['#7a3b2e', '#2f6b5e', '#5b4b8a', '#9a6b1f', '#2e5c8a', '#8a2e5c', '#4f7a2e', '#6b6b6b']
const DANGERS = ['none', 'low', 'medium', 'high']
const PILL = { w: 168, h: 22, gap: 4, head: 30 }

export const slug = (text: string) => text.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')

function unique(base: string, taken: Set<string>): string {
  let id = base || 'new'
  for (let n = 2; taken.has(id); n += 1) id = `${base}-${n}`
  return id
}

/** A road label "8h · the forest road · low" as its parts, and back. */
export function roadParts(label: string): { hours: number; terrain: string; danger: string } {
  const [hours, terrain, danger] = label.split('·').map((part) => part.trim())
  return { hours: Number.parseFloat(hours) || 8, terrain: terrain || 'the road', danger: DANGERS.includes(danger) ? danger : 'low' }
}
const roadLabel = (parts: { hours: number; terrain: string; danger: string }) => `${parts.hours}h · ${parts.terrain} · ${parts.danger}`

/** Where a town's neighborhood box and its places sit: the box centred on the neighborhood, its places listed in it. */
function boxOf(group: MapGroup, members: number) {
  const w = PILL.w + 16
  const h = PILL.head + Math.max(1, members) * (PILL.h + PILL.gap) + 8
  return { x: (group.x ?? 500) - w / 2, y: (group.y ?? 500) - h / 2, w, h }
}

/** How far to spread a town's neighborhoods out from its centre so their boxes do not overlap (directions stay
 *  true; only the drawing is spread, the saved lat/lon are not). */
function spreadOf(graph: MapGraph): number {
  const boxes = graph.groups.map((group) => ({ group, box: boxOf(group, graph.nodes.filter((node) => node.group === group.id).length) }))
  let spread = 1
  boxes.forEach((a, i) => boxes.slice(i + 1).forEach((b) => {
    const dx = Math.abs((a.group.x ?? 500) - (b.group.x ?? 500)), dy = Math.abs((a.group.y ?? 500) - (b.group.y ?? 500))
    const needX = dx ? (a.box.w + b.box.w) / 2 / dx + 0.04 : Infinity, needY = dy ? (a.box.h + b.box.h) / 2 / dy + 0.04 : Infinity
    spread = Math.max(spread, Math.min(needX, needY, 6))
  }))
  return spread
}
const spreadOut = (group: MapGroup, spread: number): MapGroup => ({ ...group, x: 500 + ((group.x ?? 500) - 500) * spread, y: 500 + ((group.y ?? 500) - 500) * spread })

/** A view that shows everything on the map, with a margin. */
function fit(graph: MapGraph, spread = 1): { x: number; y: number; w: number } {
  const boxes = graph.map === 'town'
    ? graph.groups.map((group) => boxOf(spreadOut(group, spread), graph.nodes.filter((node) => node.group === group.id).length))
    : graph.nodes.map((node) => ({ x: (node.x ?? 500) - 40, y: (node.y ?? 500) - 20, w: 80, h: 50 }))
  if (!boxes.length) return { x: -40, y: -40, w: 1080 }
  const left = Math.min(...boxes.map((box) => box.x)), top = Math.min(...boxes.map((box) => box.y))
  const right = Math.max(...boxes.map((box) => box.x + box.w)), bottom = Math.max(...boxes.map((box) => box.y + box.h))
  const w = Math.max(right - left, bottom - top, 200) + 80
  return { x: (left + right) / 2 - w / 2, y: (top + bottom) / 2 - w / 2, w }
}

/** The visual map editor: drag stops or neighborhoods, draw roads, move places between neighborhoods, with the
 *  same map as Mermaid text underneath, both kept in step. Nothing is written until Save. */
export function MapEditor({ world, kind, town }: { world: WorldRef; kind: 'travel' | 'town'; town?: string }) {
  const client = useQueryClient()
  const key = ['map', JSON.stringify(world), kind, town ?? '']
  const read = useQuery({ queryKey: key, queryFn: () => sendJson<MapGraph>('/api/maps/read', 'POST', { ...world, map: kind, town }) })
  const [graph, setGraph] = useState<MapGraph | null>(null)
  const [dirty, setDirty] = useState(false)
  const [picked, setPicked] = useState<Picked>(null)
  const [tool, setTool] = useState<'move' | 'link'>('move')
  const [linkFrom, setLinkFrom] = useState<string | null>(null)
  const [view, setView] = useState({ x: kind === 'town' ? -150 : -40, y: kind === 'town' ? -150 : -40, w: kind === 'town' ? 1300 : 1080 })
  const [drag, setDrag] = useState<Drag>(null)
  const [text, setText] = useState('')
  const [textDirty, setTextDirty] = useState(false)
  const [error, setError] = useState('')
  const [ghost, setGhost] = useState<{ x: number; y: number } | null>(null)
  const svg = useRef<SVGSVGElement>(null)

  useEffect(() => { if (read.data) { setGraph(read.data); setDirty(false); setText(read.data.mermaid ?? ''); setTextDirty(false) } }, [read.data])
  const fitted = useRef(false)
  const spread = useMemo(() => (kind === 'town' && read.data ? spreadOf(read.data) : 1), [kind, read.data])
  useEffect(() => {
    if (!read.data || fitted.current) return
    fitted.current = true
    setView(fit(read.data, spread))
  }, [read.data, spread])
  const change = (next: MapGraph) => { setGraph(next); setDirty(true); setError('') }

  // The Mermaid text follows the drawing (unless you are typing in it).
  const shown = useMemo(() => graph && JSON.stringify({ nodes: graph.nodes, groups: graph.groups, links: graph.links }), [graph])
  useEffect(() => {
    if (!graph || textDirty || !dirty) return
    const timer = setTimeout(() => {
      void sendJson<{ mermaid: string }>('/api/maps/text', 'POST', { graph, direction: kind === 'town' ? 'TB' : 'LR' })
        .then((done) => setText(done.mermaid)).catch(() => undefined)
    }, 250)
    return () => clearTimeout(timer)
  }, [shown]) // eslint-disable-line react-hooks/exhaustive-deps

  const loaded = (next: MapGraph) => { client.setQueryData(key, next); void client.invalidateQueries({ queryKey: ['town'] }); setGraph(next); setDirty(false); setText(next.mermaid ?? ''); setTextDirty(false); setError('') }
  const save = useMutation({ mutationFn: () => sendJson<MapGraph>('/api/maps/save', 'PUT', { ...world, map: kind, town, graph }), onSuccess: loaded, onError: (failure) => setError(failure.message) })
  const undo = useMutation({ mutationFn: () => sendJson<MapGraph>('/api/maps/undo', 'POST', { ...world, map: kind, town }), onSuccess: loaded, onError: (failure) => setError(failure.message) })
  const apply = useMutation({
    mutationFn: () => sendJson<MapGraph>('/api/maps/parse', 'POST', { text, graph }),
    onSuccess: (next) => { change({ ...graph!, ...next }); setTextDirty(false) }, onError: (failure) => setError(failure.message),
  })

  if (read.isError) return <p className="error">{read.error.message}</p>
  if (!graph) return <p className="muted">Loading the map…</p>
  const colorOf = (group: string | null) => {
    const index = (kind === 'travel' ? graph.regions ?? graph.groups : graph.groups).findIndex((item) => item.id === group)
    return index < 0 ? '#888' : COLORS[index % COLORS.length]
  }
  const members = (group: string) => graph.nodes.filter((node) => node.group === group)
  const at = (event: { clientX: number; clientY: number }) => {
    const matrix = svg.current?.getScreenCTM()
    if (!matrix) return { x: 0, y: 0 }
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
    return { x: point.x, y: point.y }
  }
  const nodeAt = (id: string) => graph.nodes.find((node) => node.id === id)

  // Dragging -------------------------------------------------------------------------------------------------------
  const startNode = (event: ReactPointerEvent, node: MapNode, origin: { x: number; y: number }) => {
    event.stopPropagation()
    if (tool === 'link' && kind === 'travel') {
      if (!linkFrom) { setLinkFrom(node.id); return }
      if (linkFrom !== node.id && !graph.links.some((link) => [link.from, link.to].sort().join() === [linkFrom, node.id].sort().join())) {
        change({ ...graph, links: [...graph.links, { from: linkFrom, to: node.id, label: '8h · the road · low' }] })
        setPicked({ type: 'link', index: graph.links.length })
      }
      setLinkFrom(null)
      return
    }
    const point = at(event)
    setPicked({ type: 'node', id: node.id })
    setDrag({ type: 'node', id: node.id, dx: point.x - origin.x, dy: point.y - origin.y, moved: false })
    ;(event.target as Element).setPointerCapture?.(event.pointerId)
  }
  const startGroup = (event: ReactPointerEvent, group: MapGroup) => {
    event.stopPropagation()
    const point = at(event)
    const shown = spreadOut(group, spread)
    setPicked({ type: 'group', id: group.id })
    setDrag({ type: 'group', id: group.id, dx: point.x - (shown.x ?? 500), dy: point.y - (shown.y ?? 500), moved: false })
    ;(event.target as Element).setPointerCapture?.(event.pointerId)
  }
  const move = (event: ReactPointerEvent) => {
    if (!drag) return
    const point = at(event)
    if (drag.type === 'pan') {
      const scale = view.w / (svg.current?.clientWidth || 1)
      setView((old) => ({ ...old, x: drag.from!.x - (event.clientX - drag.dx) * scale, y: drag.from!.y - (event.clientY - drag.dy) * scale }))
      return
    }
    if (drag.type === 'group') {
      const [x, y] = [500 + (point.x - drag.dx - 500) / spread, 500 + (point.y - drag.dy - 500) / spread]
      change({ ...graph, groups: graph.groups.map((group) => group.id === drag.id ? { ...group, x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 } : group) })
    } else if (kind === 'travel') {
      change({ ...graph, nodes: graph.nodes.map((node) => node.id === drag.id ? { ...node, x: Math.round(point.x - drag.dx), y: Math.round(point.y - drag.dy), placed: true } : node) })
    } else {
      setGhost({ x: point.x - drag.dx, y: point.y - drag.dy })
    }
    if (!drag.moved) setDrag({ ...drag, moved: true })
  }
  const end = (event: ReactPointerEvent) => {
    if (drag?.type === 'node' && kind === 'town' && drag.moved) {
      const point = at(event)
      const target = graph.groups.find((group) => {
        const box = boxOf(spreadOut(group, spread), members(group.id).length)
        return point.x >= box.x && point.x <= box.x + box.w && point.y >= box.y && point.y <= box.y + box.h
      })
      if (target && target.id !== nodeAt(drag.id!)?.group) {
        change({ ...graph, nodes: graph.nodes.map((node) => node.id === drag.id ? { ...node, group: target.id } : node) })
      }
    }
    setGhost(null)
    setDrag(null)
  }
  const startPan = (event: ReactPointerEvent) => {
    setPicked(null)
    setLinkFrom(null)
    setDrag({ type: 'pan', dx: event.clientX, dy: event.clientY, moved: false, from: { x: view.x, y: view.y } })
  }
  const zoom = (factor: number) => setView((old) => {
    const w = Math.min(4000, Math.max(250, old.w * factor))
    return { x: old.x + (old.w - w) / 2, y: old.y + (old.w - w) / 2, w }
  })

  // Drawing --------------------------------------------------------------------------------------------------------
  const k = view.w / 600  // labels and markers keep their size on screen as you zoom
  const travelCanvas = () => (
    <>
      {graph.links.map((link, index) => {
        const a = nodeAt(link.from), b = nodeAt(link.to)
        if (!a || !b) return null
        const isPicked = picked?.type === 'link' && picked.index === index
        const danger = roadParts(link.label).danger
        return (
          <g key={`${link.from}-${link.to}-${index}`} className={`map-link danger-${danger}${isPicked ? ' picked' : ''}`}
            onPointerDown={(event) => { event.stopPropagation(); setPicked({ type: 'link', index }) }}>
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} strokeWidth={(isPicked ? 4 : 2.5) * k} />
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="hit" strokeWidth={14 * k} />
            <text x={((a.x ?? 0) + (b.x ?? 0)) / 2} y={((a.y ?? 0) + (b.y ?? 0)) / 2 - 4 * k} textAnchor="middle" fontSize={11 * k} strokeWidth={3 * k}>{roadParts(link.label).hours}h</text>
          </g>
        )
      })}
      {graph.nodes.map((node) => (
        <g key={node.id} className={`map-stop${picked?.type === 'node' && picked.id === node.id ? ' picked' : ''}${linkFrom === node.id ? ' linking' : ''}`}
          transform={`translate(${node.x ?? 500} ${node.y ?? 500})`} onPointerDown={(event) => startNode(event, node, { x: node.x ?? 500, y: node.y ?? 500 })}>
          <circle r={(node.safe ? 8 : 5.5) * k} fill={colorOf(node.group)} strokeWidth={2 * k} />
          <text y={20 * k} textAnchor="middle" fontSize={13 * k} strokeWidth={3 * k}>{node.label}</text>
          <title>{node.label}{node.placed ? '' : ' (not placed on the world map yet: drag it to place it)'}</title>
        </g>
      ))}
    </>
  )
  const townCanvas = () => (
    <>
      {graph.groups.map((group) => {
        const inside = members(group.id)
        const box = boxOf(spreadOut(group, spread), inside.length)
        return (
          <g key={group.id} className={`map-hood${picked?.type === 'group' && picked.id === group.id ? ' picked' : ''}`}>
            <rect x={box.x} y={box.y} width={box.w} height={box.h} rx={8} style={{ stroke: colorOf(group.id) }} />
            <rect className="hood-head" x={box.x} y={box.y} width={box.w} height={PILL.head - 6} rx={8} style={{ fill: colorOf(group.id) }}
              onPointerDown={(event) => startGroup(event, group)} />
            <text className="hood-name" x={box.x + 10} y={box.y + 17} onPointerDown={(event) => startGroup(event, group)}>{group.label}</text>
            {inside.map((node, index) => {
              const x = box.x + 8, y = box.y + PILL.head + index * (PILL.h + PILL.gap)
              const isPicked = picked?.type === 'node' && picked.id === node.id
              return (
                <g key={node.id} className={`map-pill ${node.kind ?? ''}${isPicked ? ' picked' : ''}`} opacity={drag?.id === node.id && ghost ? 0.35 : 1}
                  onPointerDown={(event) => startNode(event, node, { x, y })}>
                  <rect x={x} y={y} width={PILL.w} height={PILL.h} rx={node.kind === 'place' ? 11 : 3} />
                  <text x={x + 10} y={y + 15}>{node.label.length > 24 ? `${node.label.slice(0, 23)}…` : node.label}</text>
                  <title>{node.label} ({node.kind === 'employer' ? `employer, ${node.type}` : node.type})</title>
                </g>
              )
            })}
          </g>
        )
      })}
      {ghost && drag?.id && (
        <g className="map-pill ghost" pointerEvents="none">
          <rect x={ghost.x} y={ghost.y} width={PILL.w} height={PILL.h} rx={11} />
          <text x={ghost.x + 10} y={ghost.y + 15}>{nodeAt(drag.id)?.label}</text>
        </g>
      )}
    </>
  )

  return (
    <div className="map-editor">
      <div className="map-toolbar">
        <div className="row tight" role="group" aria-label="Tool">
          <button type="button" aria-pressed={tool === 'move'} onClick={() => { setTool('move'); setLinkFrom(null) }}><MousePointer2 size={14} aria-hidden /> Move</button>
          {kind === 'travel' && <button type="button" aria-pressed={tool === 'link'} onClick={() => setTool('link')}><Link2 size={14} aria-hidden /> Draw roads</button>}
          <button type="button" aria-label="Zoom in" onClick={() => zoom(0.8)}><ZoomIn size={14} aria-hidden /></button>
          <button type="button" aria-label="Zoom out" onClick={() => zoom(1.25)}><ZoomOut size={14} aria-hidden /></button>
          <button type="button" onClick={() => setView(fit(graph, spread))}>Fit</button>
        </div>
        <div className="row tight">
          {dirty && <span className="muted small">Unsaved changes</span>}
          <button type="button" disabled={!dirty || save.isPending} onClick={() => save.mutate()}><Save size={14} aria-hidden /> Save map</button>
          <button type="button" disabled={dirty || !graph.undo?.length || undo.isPending} onClick={() => undo.mutate()}><Undo2 size={14} aria-hidden /> Undo</button>
          {dirty && <button type="button" onClick={() => read.data && loaded(read.data)}>Discard</button>}
        </div>
      </div>
      <p className="muted small">
        {kind === 'travel'
          ? tool === 'link' ? (linkFrom ? `Now click the stop the road from ${nodeAt(linkFrom)?.label} goes to.` : 'Click a stop, then another, to join them by road.')
            : 'Drag a stop to move it on the world map. Pick a road to set its hours, terrain and danger. Drag empty space to pan.'
          : 'Drag a place onto another neighborhood to move it there. Drag a neighborhood by its title to move it (this moves it on Dungeon\'s street map too).'}
      </p>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="map-body">
        <svg ref={svg} className={`map-canvas map-${kind}`} viewBox={`${view.x} ${view.y} ${view.w} ${view.w}`} role="img"
          aria-label={kind === 'travel' ? 'Travel map' : 'Town map'} onPointerDown={startPan} onPointerMove={move} onPointerUp={end} onPointerLeave={end}>
          <rect className="map-paper" x={-5000} y={-5000} width={11000} height={11000} />
          {kind === 'travel' && <rect className="map-world" x={0} y={0} width={1000} height={1000} />}
          {kind === 'travel' ? travelCanvas() : townCanvas()}
        </svg>
        <SidePanel graph={graph} kind={kind} picked={picked} setPicked={setPicked} change={change} colorOf={colorOf} />
      </div>
      <details className="map-text" open>
        <summary>Mermaid text</summary>
        <p className="muted small">The same map as a Mermaid flowchart: paste it into any Mermaid viewer, or edit it here and apply. Positions stay as drawn.</p>
        <textarea className="code" aria-label="Mermaid text" rows={12} spellCheck={false} value={text}
          onChange={(event) => { setText(event.target.value); setTextDirty(true) }} />
        <div className="row tight">
          <button type="button" disabled={!textDirty || apply.isPending} onClick={() => apply.mutate()}>Apply text to the map</button>
          {textDirty && <button type="button" onClick={() => { setTextDirty(false); setDirty(true); setGraph({ ...graph }) }}>Back to the drawing</button>}
          <button type="button" onClick={() => void navigator.clipboard?.writeText(text)}><Copy size={14} aria-hidden /> Copy</button>
        </div>
      </details>
    </div>
  )
}

function SidePanel({ graph, kind, picked, setPicked, change, colorOf }: {
  graph: MapGraph; kind: 'travel' | 'town'; picked: Picked; setPicked: (next: Picked) => void
  change: (next: MapGraph) => void; colorOf: (group: string | null) => string
}) {
  const [adding, setAdding] = useState('')
  const [name, setName] = useState('')
  const [placeKind, setPlaceKind] = useState('')
  const ids = new Set([...graph.nodes.map((node) => node.id), ...graph.groups.map((group) => group.id)])
  const node = picked?.type === 'node' ? graph.nodes.find((item) => item.id === picked.id) : undefined
  const group = picked?.type === 'group' ? graph.groups.find((item) => item.id === picked.id) : undefined
  const link = picked?.type === 'link' ? graph.links[picked.index] : undefined
  const groups = kind === 'travel' ? graph.regions ?? graph.groups : graph.groups
  const setNode = (patch: Partial<MapNode>) => node && change({ ...graph, nodes: graph.nodes.map((item) => item.id === node.id ? { ...item, ...patch } : item) })
  const setLink = (label: string) => picked?.type === 'link' && change({ ...graph, links: graph.links.map((item, index) => index === picked.index ? { ...item, label } : item) })
  const addable = (graph.addable ?? []).filter((item) => !ids.has(item.id))
  return (
    <aside className="map-side">
      {node && (
        <section>
          <h3>{kind === 'travel' ? 'Stop' : node.kind === 'employer' ? 'Employer' : 'Place'}</h3>
          <label className="field"><span>Name</span><input value={node.label} onChange={(event) => setNode({ label: event.target.value })} /></label>
          <label className="field"><span>{kind === 'travel' ? 'Region' : 'Neighborhood'}</span>
            <select value={node.group ?? ''} onChange={(event) => setNode({ group: event.target.value || null })}>
              {kind === 'travel' && <option value="">No region</option>}
              {groups.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </label>
          <p className="muted small"><code>{node.id}</code>{node.type ? ` · ${node.type}` : ''}</p>
          {node.kind !== 'employer' && (
            <button type="button" onClick={() => { change({ ...graph, nodes: graph.nodes.filter((item) => item.id !== node.id), links: graph.links.filter((item) => item.from !== node.id && item.to !== node.id) }); setPicked(null) }}>
              <Trash2 size={14} aria-hidden /> {kind === 'travel' ? 'Take off the map' : 'Remove place'}
            </button>
          )}
        </section>
      )}
      {link && (() => {
        const parts = roadParts(link.label)
        const label = (patch: Partial<typeof parts>) => setLink(roadLabel({ ...parts, ...patch }))
        return (
          <section>
            <h3>Road</h3>
            <p className="small">{graph.nodes.find((item) => item.id === link.from)?.label} to {graph.nodes.find((item) => item.id === link.to)?.label}</p>
            <label className="field"><span>Hours on foot</span><input type="number" min={0.5} step="any" value={parts.hours} onChange={(event) => label({ hours: Number(event.target.value) || 1 })} /></label>
            <label className="field"><span>Terrain</span><input value={parts.terrain} onChange={(event) => label({ terrain: event.target.value.replace(/·/g, '') })} /></label>
            <label className="field"><span>Danger</span>
              <select value={parts.danger} onChange={(event) => label({ danger: event.target.value })}>{DANGERS.map((level) => <option key={level}>{level}</option>)}</select>
            </label>
            <button type="button" onClick={() => { change({ ...graph, links: graph.links.filter((_, index) => picked?.type === 'link' && index !== picked.index) }); setPicked(null) }}>
              <Trash2 size={14} aria-hidden /> Remove road
            </button>
          </section>
        )
      })()}
      {group && (
        <section>
          <h3>Neighborhood</h3>
          <label className="field"><span>Name</span><input value={group.label} onChange={(event) => change({ ...graph, groups: graph.groups.map((item) => item.id === group.id ? { ...item, label: event.target.value } : item) })} /></label>
          <p className="muted small"><code>{group.id}</code></p>
          <button type="button" disabled={graph.nodes.some((item) => item.group === group.id)} title="Move its places out first"
            onClick={() => { change({ ...graph, groups: graph.groups.filter((item) => item.id !== group.id) }); setPicked(null) }}>
            <Trash2 size={14} aria-hidden /> Remove neighborhood
          </button>
        </section>
      )}
      {!picked && <p className="muted small">Pick something on the map to change it.</p>}
      <section className="map-add">
        <h3>Add</h3>
        {kind === 'travel' ? (
          addable.length ? (
            <form onSubmit={(event) => {
              event.preventDefault()
              const item = addable.find((found) => found.id === adding)
              if (!item) return
              change({ ...graph, nodes: [...graph.nodes, { id: item.id, label: item.label, group: null, kind: 'stop', x: 500, y: 500, placed: true, safe: item.kind === 'town' }] })
              setPicked({ type: 'node', id: item.id }); setAdding('')
            }}>
              <select aria-label="Stop to add" value={adding} onChange={(event) => setAdding(event.target.value)}>
                <option value="">A town or roadside place…</option>
                {addable.map((item) => <option key={item.id} value={item.id}>{item.label} ({item.kind})</option>)}
              </select>
              <button type="submit" disabled={!adding}><Plus size={14} aria-hidden /> Put on the map</button>
            </form>
          ) : <p className="muted small">Every town and roadside place is on the map. Make a new town with New town.</p>
        ) : (
          <form className="stack" onSubmit={(event) => {
            event.preventDefault()
            if (!name.trim()) return
            const id = unique(slug(name), ids)
            if (adding === '__hood__') {
              change({ ...graph, groups: [...graph.groups, { id, label: name.trim(), x: 500, y: 500 }] })
              setPicked({ type: 'group', id })
            } else {
              const into = adding || graph.groups[0]?.id
              change({ ...graph, nodes: [...graph.nodes, { id, label: name.trim(), group: into, kind: 'place', type: placeKind || graph.kinds?.[0] }] })
              setPicked({ type: 'node', id })
            }
            setName('')
          }}>
            <input aria-label="New name" placeholder="Name" value={name} onChange={(event) => setName(event.target.value)} />
            <select aria-label="Add to" value={adding} onChange={(event) => setAdding(event.target.value)}>
              {graph.groups.map((item) => <option key={item.id} value={item.id}>A place in {item.label}</option>)}
              <option value="__hood__">A new neighborhood</option>
            </select>
            {adding !== '__hood__' && (
              <select aria-label="Kind of place" value={placeKind} onChange={(event) => setPlaceKind(event.target.value)}>
                {(graph.kinds ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            )}
            <button type="submit" disabled={!name.trim()}><Plus size={14} aria-hidden /> Add</button>
            <p className="muted small">A new place or neighborhood copies the details of one like it. Fill in the rest on its tab after saving.</p>
          </form>
        )}
      </section>
      {kind === 'travel' && (graph.regions ?? []).length > 0 && (
        <section>
          <h3>Regions</h3>
          <ul className="legend">{(graph.regions ?? []).map((item) => <li key={item.id}><span className="swatch" style={{ background: colorOf(item.id) }} />{item.label}</li>)}</ul>
        </section>
      )}
    </aside>
  )
}
