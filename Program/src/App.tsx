import { useQuery } from '@tanstack/react-query'
import { Globe2, MessagesSquare, Hammer } from 'lucide-react'
import { getJson, type FormatSource, type Health } from './api'

/** The three panes from the build plan: the world on the left, the open thing in the middle, chat and drafts on the right. */
export function App() {
  const health = useQuery({ queryKey: ['health'], queryFn: () => getJson<Health>('/api/health') })
  const format = useQuery({ queryKey: ['format'], queryFn: () => getJson<FormatSource>('/api/format') })
  return (
    <div className="shell">
      <header className="top">
        <Hammer size={18} aria-hidden />
        <h1>Prospero's Worldsmith</h1>
        <span className="muted">{health.data ? `v${health.data.version}` : health.isError ? 'server not reachable' : '…'}</span>
      </header>
      <aside className="pane world" aria-label="World">
        <h2><Globe2 size={16} aria-hidden /> World</h2>
        <p className="muted">No world open yet. Opening a Dungeon checkout or a world folder comes next.</p>
      </aside>
      <main className="pane work">
        <h2>Town builder</h2>
        <p className="muted">Towns, shops, quests and people will open here as forms.</p>
        {format.data && (
          <p className="note">
            Writing Dungeon's world format {format.data.package_format} from{' '}
            <code>{format.data.repo}@{format.data.commit.slice(0, 7)}</code>: {format.data.sections.length} package
            sections and {format.data.engine_kinds.length} kinds of engine data.
          </p>
        )}
        {format.isError && <p className="error">{(format.error as Error).message}</p>}
      </main>
      <aside className="pane side" aria-label="Brainstorm and drafts">
        <h2><MessagesSquare size={16} aria-hidden /> Brainstorm and drafts</h2>
        <p className="muted">The world-aware chat and the queue of drafts waiting for your approval will live here.</p>
      </aside>
    </div>
  )
}
