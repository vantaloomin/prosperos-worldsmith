import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Save, Trash2, Undo2 } from 'lucide-react'
import { getJson, sendJson, type TownFiles, type WorldRef } from './api'
import { DraftButton } from './DraftButton'
import { RecordForm } from './RecordForm'
import { blankFor, CITY_SECTIONS, REFERENCES, type JsonSchema } from './schema'

type Value = Record<string, unknown>
const PARTS: { kind: string; name: string; starter: Value }[] = [
  { kind: 'items', name: 'Shops', starter: { items: [], shops: [], kits: {} } },
  { kind: 'adventures', name: 'Quest', starter: { quests: [], dangers: [] } },
  { kind: 'finds', name: 'Finds', starter: { containers: {} } },
  { kind: 'premades', name: 'Premades', starter: { premades: [] } },
]

function JsonPart({ value, onChange }: { value: Value; onChange: (next: Value) => void }) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2))
  const [bad, setBad] = useState('')
  return (
    <>
      <textarea aria-label="File contents" className={`code tall${bad ? ' bad' : ''}`} value={text} spellCheck={false}
        onChange={(event) => {
          setText(event.target.value)
          try {
            const parsed = JSON.parse(event.target.value)
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) { onChange(parsed); setBad('') } else setBad('It needs to be one JSON object.')
          } catch (error) { setBad(error instanceof Error ? error.message : 'Not valid JSON yet.') }
        }} />
      {bad && <p className="error small">{bad} The last valid version is what Save would write.</p>}
    </>
  )
}

function Section({ city, root, section, onChange, choicesFor }: {
  city: Value; root: JsonSchema; section: string; onChange: (next: Value) => void; choicesFor: (field: string) => string[] | undefined
}) {
  const items = (city[section] as Value[] | undefined) ?? []
  const [chosen, setChosen] = useState(0)
  const itemSchema = (root.properties?.[section]?.items ?? {}) as JsonSchema
  const write = (next: Value[]) => onChange({ ...city, [section]: next })
  const add = () => {
    const sources = Object.keys((city.sources as Value | undefined) ?? {})
    const blank = blankFor(itemSchema, root, { id: `new-${section.replace(/_/g, '-')}-${items.length + 1}`, source: sources[0] ?? '' })
    write([...items, blank])
    setChosen(items.length)
  }
  const index = Math.min(chosen, items.length - 1)
  return (
    <div className="section">
      <div className="entries">
        <ul className="choices">
          {items.map((item, at) => (
            <li key={`${String(item.id ?? item.item ?? at)}-${at}`}>
              <button type="button" aria-pressed={at === index} onClick={() => setChosen(at)}>
                <strong>{String(item.name ?? item.item ?? item.id ?? `Entry ${at + 1}`)}</strong>
                {typeof item.id === 'string' && <span className="muted small">{item.id}</span>}
              </button>
            </li>
          ))}
        </ul>
        <button type="button" onClick={add}><Plus size={14} aria-hidden /> Add</button>
      </div>
      {index >= 0 && items[index] ? (
        <div className="entry">
          <div className="entry-head">
            <h3>{String(items[index].name ?? items[index].id ?? '')}</h3>
            <button type="button" onClick={() => { write(items.filter((_, at) => at !== index)); setChosen(Math.max(0, index - 1)) }}>
              <Trash2 size={14} aria-hidden /> Remove
            </button>
          </div>
          <RecordForm key={`${section}-${index}`} schema={itemSchema} root={root} value={items[index]} choicesFor={choicesFor}
            onChange={(next) => write(items.map((item, at) => (at === index ? next : item)))} />
        </div>
      ) : <p className="muted">Nothing here yet.</p>}
    </div>
  )
}

/** A town's files as forms: the city file from Dungeon's own schema, the other parts as JSON for now. */
export function TownEditor({ world, town }: { world: WorldRef; town: string }) {
  const client = useQueryClient()
  const key = ['town', JSON.stringify(world), town]
  const files = useQuery({ queryKey: key, queryFn: () => sendJson<TownFiles>('/api/towns/read', 'POST', { ...world, town }) })
  const schema = useQuery({ queryKey: ['city-schema'], queryFn: () => getJson<JsonSchema>('/api/schema/city'), staleTime: Infinity })
  const [tab, setTab] = useState('town')
  const [drafts, setDrafts] = useState<Record<string, Value>>({})
  useEffect(() => { setDrafts({}); setTab('town') }, [town])
  const loaded = (next: TownFiles) => { client.setQueryData(key, next); setDrafts({}) }
  const save = useMutation({
    mutationFn: (kind: string) => sendJson<TownFiles>('/api/towns/part', 'PUT', { ...world, town, kind, data: drafts[kind] }),
    onSuccess: loaded,
  })
  const undo = useMutation({ mutationFn: () => sendJson<TownFiles>('/api/towns/undo', 'POST', { ...world, town }), onSuccess: loaded })
  const city = (drafts.cities ?? files.data?.parts.cities ?? {}) as Value
  const choicesFor = useMemo(() => (field: string) => {
    const from = REFERENCES[field]
    if (!from) return undefined
    if (from === 'sources') return Object.keys((city.sources as Value | undefined) ?? {})
    return ((city[from] as Value[] | undefined) ?? []).map((item) => String(item.id))
  }, [city])
  if (files.isError) return <p className="error">{files.error.message}</p>
  if (!files.data || !schema.data) return <p className="muted">Loading the town…</p>
  const root = schema.data
  const kindOf = tab === 'town' || CITY_SECTIONS.some((section) => section.key === tab) ? 'cities' : tab
  const part = PARTS.find((item) => item.kind === kindOf)
  const current = (drafts[kindOf] ?? files.data.parts[kindOf]) as Value | null
  const dirty = Object.keys(drafts)
  const setDraft = (kind: string, next: Value) => setDrafts((all) => ({ ...all, [kind]: next }))
  const problems = files.data.problems[kindOf] ?? []
  return (
    <div className="town">
      <div className="town-head">
        <h2>{String(city.name ?? town)}</h2>
        <div className="actions">
          {dirty.length > 0 && <span className="muted small">Unsaved: {dirty.map((kind) => PARTS.find((item) => item.kind === kind)?.name ?? 'town').join(', ')}</span>}
          <button type="button" disabled={!drafts[kindOf] || save.isPending} onClick={() => save.mutate(kindOf)}><Save size={14} aria-hidden /> Save</button>
          <button type="button" disabled={!files.data.undo.length || undo.isPending || dirty.length > 0}
            title={files.data.undo[0] ? `Undo the ${files.data.undo[0].at} save` : 'Nothing to undo'} onClick={() => undo.mutate()}>
            <Undo2 size={14} aria-hidden /> Undo
          </button>
        </div>
      </div>
      <nav className="tabs" aria-label="Town parts">
        {[{ key: 'town', name: 'Town' }, ...CITY_SECTIONS, ...PARTS.map((item) => ({ key: item.kind, name: item.name }))].map((item) => (
          <button key={item.key} type="button" aria-pressed={tab === item.key} onClick={() => setTab(item.key)}>{item.name}</button>
        ))}
      </nav>
      {(save.isError || undo.isError) && <p className="error" role="alert">{(save.error ?? undo.error)?.message}</p>}
      {problems.length > 0 && !drafts[kindOf] && (
        <div className="problems" role="alert"><ul>{problems.slice(0, 12).map((problem) => <li key={problem}>{problem}</li>)}</ul></div>
      )}
      {tab === 'town' && (
        <RecordForm schema={root} root={root} value={city} choicesFor={choicesFor} onChange={(next) => setDraft('cities', next)}
          skip={['schema_version', 'id', 'sources', ...CITY_SECTIONS.map((section) => section.key)]} />
      )}
      {CITY_SECTIONS.map((section) => tab === section.key && (
        <div key={section.key}>
          <p className="muted small">{section.label}.</p>
          <DraftButton world={world} town={town} target={section.key} what={section.name.toLowerCase()} />
          <Section city={city} root={root} section={section.key} choicesFor={choicesFor} onChange={(next) => setDraft('cities', next)} />
        </div>
      ))}
      {part?.kind === 'adventures' && current && <DraftButton world={world} town={town} target="quests" what="quests" />}
      {part?.kind === 'premades' && current && <DraftButton world={world} town={town} target="premades" what="premade characters" />}
      {part && (current ? <JsonPart key={`${part.kind}-${files.dataUpdatedAt}`} value={current} onChange={(next) => setDraft(part.kind, next)} />
        : (
          <div>
            <p className="muted">{String(city.name ?? town)} has no {part.name.toLowerCase()} file yet.</p>
            <button type="button" onClick={() => setDraft(part.kind, part.starter)}><Plus size={14} aria-hidden /> Start one</button>
          </div>
        ))}
    </div>
  )
}
