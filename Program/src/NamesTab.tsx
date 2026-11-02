import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Dices } from 'lucide-react'
import { sendJson } from './api'

type Value = Record<string, unknown>
interface NamesView {
  banks: Record<string, string[]>
  era_bank: string
  spread: { bank: string; given: number; family: number; groups: { id: string; weight: number; own: boolean }[] }
  samples: { name: string; group: string }[]
}

/** How a town names its people, from Dungeon's own name banks: the bank, each heritage's weight, and samples. */
export function NamesTab({ city, onChange }: { city: Value; onChange: (next: Value) => void }) {
  const [seed, setSeed] = useState(1)
  const names = (city.names as Value | null | undefined) ?? {}
  const era = String(city.era ?? 'modern')
  const view = useQuery({
    queryKey: ['names', era, JSON.stringify(names), seed],
    queryFn: () => sendJson<NamesView>('/api/names/view', 'POST', { era, names, seed: String(seed) }),
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
        {samples.map((item, at) => <li key={at}>{item.name} <span className="muted small">{item.group}</span></li>)}
      </ul>
    </div>
  )
}
