import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Dices } from 'lucide-react'
import { sendJson } from './api'

type Value = Record<string, unknown>
interface NamesView {
  banks: Record<string, string[]>
  era_bank: string
  spread: { bank: string; given: number; family: number; groups: { id: string; weight: number; own: boolean }[] }
  samples: { name: string; group: string; kind: string | null }[]
  peoples: People[]
  shares: Record<string, number>
}
interface People { id: string; label: string; lifespan: number | null; folk: string; type: string }

/** How a town names its people, from Dungeon's own name banks: the bank, each heritage's weight, and samples. */
export function NamesTab({ city, onChange }: { city: Value; onChange: (next: Value) => void }) {
  const [seed, setSeed] = useState(1)
  const names = (city.names as Value | null | undefined) ?? {}
  const era = String(city.era ?? 'modern')
  const kinds = (city.kinds && typeof city.kinds === 'object' ? city.kinds : {}) as Record<string, Value>
  const view = useQuery({
    queryKey: ['names', era, JSON.stringify(names), JSON.stringify(kinds), seed],
    queryFn: () => sendJson<NamesView>('/api/names/view', 'POST', { era, names, kinds, seed: String(seed) }),
    placeholderData: (previous) => previous,
  })
  if (view.isError) return <p className="error">{view.error.message}</p>
  if (!view.data) return <p className="muted">Loading the name banks…</p>
  const { banks, spread, samples, era_bank: eraBank } = view.data
  const own = Object.keys((names.groups as Value | undefined) ?? {})
  const weights = Object.fromEntries(spread.groups.map((group) => [group.id, group.weight]))
  const groups = [...(banks[spread.bank] ?? []), ...own.filter((id) => !(banks[spread.bank] ?? []).includes(id))]
  const set = (patch: Value) => onChange({ ...city, names: { ...names, ...patch } })
  const weigh = (id: string, weight: number) => {
    const mix: Record<string, number> = { ...weights, [id]: weight }
    set({ mix: Object.fromEntries(Object.entries(mix).filter(([, value]) => value > 0)) })
  }
  return (
    <div className="names-tab">
      <p className="muted small">Townsfolk and NPC names come from Dungeon's name banks: about 200 given and 100 family names to a
        heritage, and for modern towns the names people were actually given in the year they were born. Pick the bank, then
        weigh its heritages. A group of the town's own (for a people no bank has) is edited on the Town tab under names.</p>
      <div className="row">
        <label className="small-field"><span>Bank</span>
          <select aria-label="Name bank" value={String(names.bank ?? '')} onChange={(event) => set({ bank: event.target.value || null, mix: {} })}>
            <option value="">The era's own ({eraBank})</option>
            {Object.keys(banks).map((bank) => <option key={bank} value={bank}>{bank}</option>)}
          </select>
        </label>
        <span className="muted small">Draws on {spread.given} given and {spread.family} family names from {spread.groups.length} group{spread.groups.length === 1 ? '' : 's'}.</span>
      </div>
      <table className="counts names-mix">
        <thead><tr><th>Heritage</th><th>Weight</th><th /></tr></thead>
        <tbody>
          {groups.map((id) => (
            <tr key={id}>
              <th>{id}{own.includes(id) && <span className="muted small"> (the town's own)</span>}</th>
              <td><input aria-label={`Weight of ${id}`} type="number" min={0} step="any" value={weights[id] ?? 0}
                onChange={(event) => weigh(id, Number(event.target.value))} /></td>
              <td className="muted small">{weights[id] ? `${Math.round(100 * weights[id] / Object.values(weights).reduce((a, b) => a + b, 0))}%` : 'not used'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>Sample townsfolk <button type="button" onClick={() => setSeed(seed + 1)}><Dices size={14} aria-hidden /> Another dozen</button></h3>
      <ul className="samples">
        {samples.map((item, at) => <li key={at}>{item.name} <span className="muted small">{item.kind ?? item.group}</span></li>)}
      </ul>
      <PeoplesPicker city={city} kinds={kinds} peoples={view.data.peoples} shares={view.data.shares} onChange={onChange} />
    </div>
  )
}

/** Which peoples live in the town and what share of its folk each is (a city's `kinds` block, as Dungeon reads it):
 * humans are the rest. Each people takes its names from its own naming scheme in Dungeon's peoples bank. */
function PeoplesPicker({ city, kinds, peoples, shares, onChange }: {
  city: Value; kinds: Record<string, Value>; peoples: People[]; shares: Record<string, number>; onChange: (next: Value) => void
}) {
  const [filter, setFilter] = useState('')
  const labels = Object.fromEntries(peoples.map((item) => [item.id, item.label]))
  const own = Object.keys(kinds).filter((id) => !(id in labels)).map((id) => ({
    id, label: String(kinds[id]?.label ?? id), lifespan: (kinds[id]?.lifespan as number | null | undefined) ?? null,
    folk: "The town's own", type: "The town's own" }))
  const all = [...peoples, ...own]
  const humans = Math.max(0, 1 - Object.values(shares).reduce((a, b) => a + b, 0))
  const setShare = (id: string, percent: number) => {
    const next: Record<string, Value> = { ...kinds }
    const entry = { ...(next[id] ?? {}) }
    // A kind left in the block with no share would get Dungeon's default share, so one with more than a share keeps 0.
    if (percent > 0) entry.share = Math.min(percent, 100) / 100
    else delete entry.share
    if (Object.keys(entry).length && !(percent > 0)) entry.share = 0
    if (Object.keys(entry).filter((key) => key !== 'share').length || percent > 0) next[id] = entry
    else delete next[id]
    onChange({ ...city, kinds: Object.keys(next).length ? next : null })
  }
  const shown = all.filter((item) => !filter || `${item.label} ${item.type} ${item.folk}`.toLowerCase().includes(filter.toLowerCase()))
  const folks = [...new Set(shown.map((item) => item.folk))]
  const percent = (id: string) => (typeof kinds[id]?.share === 'number' ? Math.round((kinds[id].share as number) * 1000) / 10 : '')
  return (
    <section className="peoples">
      <h3>Peoples</h3>
      <p className="muted small">Who lives here besides humans, and what share of the townsfolk each people is. Humans are the
        rest. Each people has its own lifespan and its own naming scheme, so a dwarf is never a Baker.</p>
      <p className="small">
        {Object.keys(shares).length === 0 ? 'Everyone here is human.' : <>
          Humans {Math.round(humans * 100)}%
          {Object.entries(shares).map(([id, share]) => <span key={id}>, {labels[id] ?? String(kinds[id]?.label ?? id)} {Math.round(share * 1000) / 10}%</span>)}
        </>}
      </p>
      <input aria-label="Find a people" placeholder="Find a people (elf, canid, oni…)" value={filter} onChange={(event) => setFilter(event.target.value)} />
      {folks.map((folk) => (
        <details key={folk} open={Boolean(filter) || shown.some((item) => item.folk === folk && percent(item.id) !== '')}>
          <summary>{folk} <span className="muted small">({shown.filter((item) => item.folk === folk).length})</span></summary>
          <table className="counts names-mix">
            <thead><tr><th>People</th><th>Kind</th><th>Lives</th><th>Share %</th></tr></thead>
            <tbody>
              {shown.filter((item) => item.folk === folk).map((item) => (
                <tr key={item.id}>
                  <th>{item.label}</th>
                  <td className="muted small">{item.type}</td>
                  <td className="muted small">{item.lifespan === null ? "doesn't age" : `about ${item.lifespan} years`}</td>
                  <td><input aria-label={`Share of ${item.label}`} type="number" min={0} max={100} step="any" value={percent(item.id)}
                    onChange={(event) => setShare(item.id, Number(event.target.value))} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ))}
    </section>
  )
}
