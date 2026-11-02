import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { CircleCheck, Dices, ShieldCheck } from 'lucide-react'
import { sendJson, type WorldRef } from './api'

type Point = [number, number]
interface Thing { id: string; name: string; kind: string; summary?: string }
export interface TownMap {
  town: string; name: string; style: 'ink' | 'street' | 'floor'; walls: boolean; size: number
  patches: { id: number; kind: string; neighborhood: string | null; polygon: Point[]; place: Thing | null }[]
  streets: [Point, Point][]; roads: Point[][]
  water: { name: string; width: number; points: Point[] }[]
  lots: { id: string; neighborhood: string; front: boolean; place: Thing | null; polygon: Point[] }[]
  districts: { id: string; name: string; label: Point; patches: number[] }[]
  exits: { id: string; name: string; at: Point | null }[]; square: number; border: [Point, Point][]
}
interface Checked { ok: boolean; problems: string[]; map?: TownMap; map_problem?: string }

const points = (polygon: Point[]) => polygon.map(([x, y]) => `${x},${y}`).join(' ')
const middle = (polygon: Point[]): Point => {
  const n = polygon.length || 1
  return [polygon.reduce((sum, [x]) => sum + x, 0) / n, polygon.reduce((sum, [, y]) => sum + y, 0) / n]
}

/** The street map as Dungeon's Town widget draws it, with every place named (Dungeon hides the ones a character
 *  has not found; an author sees them all). */
export function TownMapView({ map }: { map: TownMap }) {
  const [picked, setPicked] = useState<Thing | null>(null)
  const [zoom, setZoom] = useState(1)
  const whole = map.size * 1.5
  const span = whole / zoom
  const focus = picked && [...map.lots.filter((lot) => lot.place?.id === picked.id).map((lot) => middle(lot.polygon)),
    ...map.patches.filter((patch) => patch.place?.id === picked.id).map((patch) => middle(patch.polygon))][0]
  const on = focus ?? [0, 0]
  const clamp = (value: number) => Math.max(-whole / 2, Math.min(whole / 2 - span, value - span / 2))
  const [left, top] = [clamp(on[0]), clamp(on[1])]
  const named = [...map.lots.filter((lot) => lot.place).map((lot) => ({ thing: lot.place!, at: middle(lot.polygon) })),
    ...map.patches.filter((patch) => patch.place).map((patch) => ({ thing: patch.place!, at: middle(patch.polygon) }))]
  return (
    <div className="map-view">
      <div className="row tight" role="group" aria-label="Zoom">
        {[1, 2, 4].map((level) => (
          <button key={level} type="button" aria-pressed={zoom === level} onClick={() => setZoom(level)}>
            {level === 1 ? 'Whole town' : `×${level}`}
          </button>
        ))}
      </div>
      <svg className={`town-map town-${map.style}`} viewBox={`${left.toFixed(1)} ${top.toFixed(1)} ${span.toFixed(1)} ${span.toFixed(1)}`}
        role="img" aria-label={`Street map of ${map.name}`} style={{ ['--town-scale' as string]: span / (map.size * 1.5) }}>
        <rect className="town-ground" x={-map.size * 1.2} y={-map.size * 1.2} width={map.size * 2.4} height={map.size * 2.4} />
        {map.patches.map((patch) => (
          <polygon key={patch.id} className={`town-patch patch-${patch.kind}`} points={points(patch.polygon)}
            onClick={() => setPicked(patch.place)}>{patch.place && <title>{patch.place.name}</title>}</polygon>
        ))}
        {map.water.map((water) => (
          <polyline key={water.name} className="town-river" points={points(water.points)} strokeWidth={water.width}><title>{water.name}</title></polyline>
        ))}
        {map.walls && <g className="town-wall">{map.border.map(([a, b]) => <line key={`${a}-${b}`} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} />)}</g>}
        {map.roads.map((road, index) => <polyline key={index} className="town-road" points={points(road)} />)}
        {map.lots.map((lot) => (
          <polygon key={lot.id} points={points(lot.polygon)}
            className={['town-lot', lot.place && 'named', lot.place && lot.place.id === picked?.id && 'picked'].filter(Boolean).join(' ')}
            onClick={() => setPicked(lot.place)}><title>{lot.place?.name ?? 'A blank building: Dungeon fills it when a player looks'}</title></polygon>
        ))}
        {map.districts.map((district) => (
          <text key={district.id} className="town-district" x={district.label[0]} y={district.label[1]} textAnchor="middle">{district.name}</text>
        ))}
        {zoom > 1 && named.map(({ thing, at }) => (
          <text key={thing.id} className="town-label" x={at[0]} y={at[1] - 2.5} textAnchor="middle">{thing.name}</text>
        ))}
        {map.exits.map((exit) => exit.at && (
          <text key={exit.id} className="town-exit" x={exit.at[0]} y={exit.at[1]} textAnchor="middle">to {exit.name}</text>
        ))}
      </svg>
      <p className="small">
        {picked ? <><strong>{picked.name}</strong> <span className="muted">{picked.kind}</span>{picked.summary && <><br /><span className="muted">{picked.summary}</span></>}</>
          : <span className="muted">Pick a building or open ground to see what is there. Grey buildings are blank lots Dungeon fills in play.</span>}
      </p>
      <select aria-label="Find a place" value={picked?.id ?? ''} onChange={(event) => setPicked(named.find((item) => item.thing.id === event.target.value)?.thing ?? null)}>
        <option value="">Find a place…</option>
        {named.map(({ thing }) => thing).sort((a, b) => a.name.localeCompare(b.name)).map((thing) => <option key={thing.id} value={thing.id}>{thing.name}</option>)}
      </select>
    </div>
  )
}

/** The saved town run through Dungeon's own loader (from the checkout in Settings), and its street map. */
export function DungeonCheck({ world, town, withMap, unsaved }: { world: WorldRef; town: string; withMap: boolean; unsaved: boolean }) {
  const [seed, setSeed] = useState('worldsmith')
  const check = useMutation({
    mutationFn: (next: string) => sendJson<Checked>('/api/towns/check', 'POST', { ...world, town, map: withMap, seed: next }),
  })
  const run = (next: string) => { setSeed(next); check.mutate(next) }
  return (
    <div className="dungeon-check">
      <div className="row tight">
        <button type="button" disabled={check.isPending} onClick={() => run(seed)}>
          <ShieldCheck size={14} aria-hidden /> {check.isPending ? 'Asking Dungeon…' : withMap ? 'Draw the street map' : 'Check with Dungeon'}
        </button>
        {withMap && check.data?.map && (
          <button type="button" disabled={check.isPending} onClick={() => run(Math.random().toString(36).slice(2, 8))}>
            <Dices size={14} aria-hidden /> Another campaign's layout
          </button>
        )}
        {unsaved && <span className="muted small">Checks the saved file: save first to include your changes.</span>}
      </div>
      {withMap && !check.data && !check.isPending && (
        <p className="muted small">Dungeon lays out a street map from the town's neighborhoods and places, different for each campaign. This runs Dungeon's own map engine from your checkout.</p>
      )}
      {check.isError && <p className="error" role="alert">{check.error.message}</p>}
      {check.data && (check.data.ok
        ? <p className="ok"><CircleCheck size={14} aria-hidden /> Dungeon loads this town as it is.</p>
        : <div className="problems" role="alert"><h3>Dungeon refuses this town</h3><ul>{check.data.problems.map((problem) => <li key={problem}>{problem}</li>)}</ul></div>)}
      {withMap && check.data?.map_problem && <p className="muted">{check.data.map_problem}</p>}
      {withMap && check.data?.map && <TownMapView key={seed} map={check.data.map} />}
    </div>
  )
}
