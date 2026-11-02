import { useState } from 'react'
import { fieldKind, resolve, type JsonSchema } from './schema'

type Value = Record<string, unknown>

function JsonField({ value, onChange, label }: { value: unknown; onChange: (next: unknown) => void; label: string }) {
  const [text, setText] = useState(() => JSON.stringify(value ?? null, null, 2))
  const [bad, setBad] = useState(false)
  return (
    <>
      <textarea aria-label={label} className={`code${bad ? ' bad' : ''}`} rows={Math.min(12, text.split('\n').length + 1)} value={text}
        onChange={(event) => {
          setText(event.target.value)
          try { onChange(JSON.parse(event.target.value)); setBad(false) } catch { setBad(true) }
        }} />
      {bad && <span className="error small">Not valid JSON yet; the last valid value is kept.</span>}
    </>
  )
}

/** One field drawn from its schema; `choices` offers ids of other records for reference fields. */
function Field({ name, schema, root, value, onChange, choices }: {
  name: string; schema: JsonSchema; root: JsonSchema; value: unknown; onChange: (next: unknown) => void; choices?: string[]
}) {
  const kind = fieldKind(schema, root)
  const resolved = resolve(schema, root)
  const label = resolved.title ?? name
  if (choices && (kind === 'text' || kind === 'long')) {
    return (
      <select aria-label={label} value={String(value ?? '')} onChange={(event) => onChange(event.target.value || undefined)}>
        <option value="">(none)</option>
        {choices.map((choice) => <option key={choice} value={choice}>{choice}</option>)}
        {value && !choices.includes(String(value)) ? <option value={String(value)}>{String(value)} (missing)</option> : null}
      </select>
    )
  }
  if (choices && kind === 'list') {
    const picked = (value as string[] | undefined) ?? []
    return (
      <div className="ticks">
        {choices.map((choice) => (
          <label key={choice}><input type="checkbox" checked={picked.includes(choice)}
            onChange={(event) => onChange(event.target.checked ? [...picked, choice] : picked.filter((item) => item !== choice))} /> {choice}</label>
        ))}
      </div>
    )
  }
  switch (kind) {
    case 'choice':
      return (
        <select aria-label={label} value={String(value ?? '')} onChange={(event) => onChange(event.target.value)}>
          {resolved.enum?.map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      )
    case 'choices': {
      const picked = (value as string[] | undefined) ?? []
      const options = resolve(resolved.items ?? {}, root).enum ?? []
      return (
        <div className="ticks">
          {options.map((option) => (
            <label key={option}><input type="checkbox" checked={picked.includes(option)}
              onChange={(event) => onChange(event.target.checked ? [...picked, option] : picked.filter((item) => item !== option))} /> {option}</label>
          ))}
        </div>
      )
    }
    case 'list':
      return <textarea aria-label={label} rows={3} value={((value as string[] | undefined) ?? []).join('\n')}
        placeholder="One per line" onChange={(event) => onChange(event.target.value.split('\n').filter((line) => line.trim()))} />
    case 'number':
      return <input aria-label={label} type="number" step="any" value={value === undefined || value === null ? '' : String(value)}
        onChange={(event) => onChange(event.target.value === '' ? undefined : Number(event.target.value))} />
    case 'boolean':
      return <input aria-label={label} type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />
    case 'long':
      return <textarea aria-label={label} rows={3} value={String(value ?? '')} onChange={(event) => onChange(event.target.value)} />
    case 'text':
      return <input aria-label={label} value={String(value ?? '')} onChange={(event) => onChange(event.target.value)} />
    default:
      return <JsonField label={label} value={value} onChange={onChange} />
  }
}

/** A record's fields as a form, required ones first; unset optional fields stay out of the saved file. */
export function RecordForm({ schema, root, value, onChange, choicesFor, skip = [] }: {
  schema: JsonSchema; root: JsonSchema; value: Value; onChange: (next: Value) => void
  choicesFor: (field: string) => string[] | undefined; skip?: string[]
}) {
  const resolved = resolve(schema, root)
  const required = new Set(resolved.required ?? [])
  const names = Object.keys(resolved.properties ?? {}).filter((name) => !skip.includes(name))
  names.sort((a, b) => Number(required.has(b)) - Number(required.has(a)))
  const set = (name: string, next: unknown) => {
    const copy = { ...value }
    if (next === undefined || (next === '' && !required.has(name))) delete copy[name]
    else copy[name] = next
    onChange(copy)
  }
  return (
    <div className="record">
      {names.map((name) => (
        <div key={name} className="field">
          <span>{resolve(resolved.properties![name], root).title ?? name}{required.has(name) && <b aria-label="required"> *</b>}</span>
          <Field name={name} schema={resolved.properties![name]} root={root} value={value[name]}
            onChange={(next) => set(name, next)} choices={choicesFor(name)} />
        </div>
      ))}
    </div>
  )
}
