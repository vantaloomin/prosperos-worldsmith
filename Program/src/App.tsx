import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Globe2, Hammer, MessagesSquare, TriangleAlert, X } from 'lucide-react'
import { getJson, sendJson, type FormatSource, type Health, type Town, type WorldOverview, type WorldRef } from './api'
import { TownEditor } from './TownEditor'
import { WorldPicker } from './WorldPicker'

function TownList({ towns, chosen, onChoose }: { towns: Town[]; chosen: string; onChoose: (id: string) => void }) {
  const [real, roads] = [towns.filter((town) => !town.road), towns.filter((town) => town.road)]
  return (
    <>
      <h3>Towns</h3>
      <ul className="choices">
        {real.map((town) => (
          <li key={town.id}>
            <button type="button" aria-pressed={chosen === town.id} onClick={() => onChoose(town.id)}>
              <strong>{town.name}</strong>
              <span className="muted">{town.places} places, {town.notables} notables</span>
            </button>
          </li>
        ))}
      </ul>
      {!!roads.length && <p className="muted small">Roads and wilds: {roads.map((town) => town.name).join(', ')}</p>}
    </>
  )
}

function Overview({ overview }: { overview: WorldOverview }) {
  return (
    <>
      <h2>{overview.world.name}</h2>
      {overview.world.pitch && <p>{overview.world.pitch}</p>}
      <p className="muted small">{overview.kind === 'builtin' ? 'Built-in world in your Dungeon checkout' : 'World folder'}: <code>{overview.folder}</code></p>
      {overview.problems.length > 0 && (
        <div className="problems" role="alert">
          <h3><TriangleAlert size={15} aria-hidden /> {overview.problems.length} problem{overview.problems.length === 1 ? '' : 's'} Dungeon would refuse</h3>
          <ul>{overview.problems.slice(0, 30).map((problem) => <li key={problem}>{problem}</li>)}</ul>
        </div>
      )}
      <h3>What it holds</h3>
      <table className="counts">
        <tbody>
          {Object.entries(overview.sections).map(([name, count]) => (
            <tr key={name}><th>{name}</th><td>{count.entries}</td><td className="muted">{count.hidden ? `${count.hidden} hiding a truth` : ''}</td></tr>
          ))}
          {Object.entries(overview.engine).map(([kind, count]) => (
            <tr key={kind}><th>engine: {kind}</th><td>{count}</td><td /></tr>
          ))}
          <tr><th>documents</th><td>{overview.documents}</td><td /></tr>
        </tbody>
      </table>
    </>
  )
}

/** The three panes from the build plan: the world on the left, the open thing in the middle, chat and drafts on the right. */
export function App() {
  const health = useQuery({ queryKey: ['health'], queryFn: () => getJson<Health>('/api/health') })
  const format = useQuery({ queryKey: ['format'], queryFn: () => getJson<FormatSource>('/api/format') })
  const [town, setTown] = useState('')
  const [ref, setRef] = useState<WorldRef | null>(null)
  const open = useMutation({
    mutationFn: (next: WorldRef) => sendJson<WorldOverview>('/api/worlds/open', 'POST', next),
    onSuccess: (_, next) => { setTown(''); setRef(next) },
  })
  const overview = open.data
  const chosen = overview?.towns.find((item) => item.id === town)
  return (
    <div className="shell">
      <header className="top">
        <Hammer size={18} aria-hidden />
        <h1>Prospero's Worldsmith</h1>
        <span className="muted">
          {format.data && <>Dungeon format {format.data.package_format} @ <code>{format.data.commit.slice(0, 7)}</code> · </>}
          {health.data ? `v${health.data.version}` : health.isError ? 'server not reachable' : '…'}
        </span>
      </header>
      <aside className="pane world" aria-label="World">
        <h2><Globe2 size={16} aria-hidden /> {overview ? overview.world.name : 'Open a world'}
          {overview && <button type="button" className="icon" aria-label="Close world" onClick={() => open.reset()}><X size={14} /></button>}
        </h2>
        {overview ? <TownList towns={overview.towns} chosen={town} onChoose={(id) => setTown(id === town ? '' : id)} />
          : <WorldPicker onOpen={(ref) => open.mutate(ref)} busy={open.isPending} />}
        {open.isError && <p className="error">{open.error.message}</p>}
      </aside>
      <main className="pane work">
        {chosen && ref ? <TownEditor world={ref} town={chosen.id} /> : overview ? <Overview overview={overview} />
          : <><h2>Town builder</h2><p className="muted">Open a built-in world from your Dungeon checkout, or a world folder, to start.</p></>}
      </main>
      <aside className="pane side" aria-label="Brainstorm and drafts">
        <h2><MessagesSquare size={16} aria-hidden /> Brainstorm and drafts</h2>
        <p className="muted">The world-aware chat and the queue of drafts waiting for your approval will live here.</p>
      </aside>
    </div>
  )
}
