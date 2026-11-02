import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Cpu } from 'lucide-react'
import { getJson, sendJson, type ModelConfig } from './api'

const PROVIDER_NAMES = { anthropic: 'Claude (Anthropic API)', openai: 'OpenAI-compatible server', 'claude-cli': 'claude command line' }

/** Which model drafts: shown in one line, edited in place. Keys go to the system keyring, never the settings file. */
export function ModelSettings() {
  const client = useQueryClient()
  const current = useQuery({ queryKey: ['models'], queryFn: () => getJson<ModelConfig>('/api/models') })
  const [editing, setEditing] = useState<ModelConfig & { key: string } | null>(null)
  const save = useMutation({
    mutationFn: (form: ModelConfig & { key: string }) => sendJson<ModelConfig>('/api/models', 'PUT',
      { provider: form.provider, model: form.model, base_url: form.base_url, key: form.key ? form.key : null }),
    onSuccess: (next) => { client.setQueryData(['models'], next); setEditing(null) },
  })
  if (!current.data) return null
  if (!editing) {
    return (
      <p className="model-line small">
        <Cpu size={14} aria-hidden /> {PROVIDER_NAMES[current.data.provider]}{current.data.model && <> · <code>{current.data.model}</code></>}
        <button type="button" className="link" onClick={() => setEditing({ ...current.data, key: '' })}>Change</button>
      </p>
    )
  }
  return (
    <form className="model-form" onSubmit={(event) => { event.preventDefault(); save.mutate(editing) }}>
      <select aria-label="Provider" value={editing.provider} onChange={(event) => setEditing({ ...editing, provider: event.target.value as ModelConfig['provider'] })}>
        {Object.entries(PROVIDER_NAMES).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
      </select>
      <input aria-label="Model" placeholder={editing.provider === 'anthropic' ? 'claude-opus-5-5' : 'Model name'} value={editing.model}
        onChange={(event) => setEditing({ ...editing, model: event.target.value })} />
      {editing.provider === 'openai' && (
        <input aria-label="Server address" placeholder="http://127.0.0.1:1234/v1" value={editing.base_url}
          onChange={(event) => setEditing({ ...editing, base_url: event.target.value })} />
      )}
      {editing.provider !== 'claude-cli' && (
        <input aria-label="API key" type="password" placeholder={current.data.has_key ? 'Key saved (leave blank to keep)' : 'API key (optional for local servers)'}
          value={editing.key} onChange={(event) => setEditing({ ...editing, key: event.target.value })} />
      )}
      <div className="row">
        <button type="submit" disabled={save.isPending}>Save</button>
        <button type="button" onClick={() => setEditing(null)}>Cancel</button>
      </div>
      {save.isError && <p className="error small">{save.error.message}</p>}
    </form>
  )
}
