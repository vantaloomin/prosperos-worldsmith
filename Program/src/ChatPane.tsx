import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Send, Sparkles, Trash2 } from 'lucide-react'
import { sendJson, type ChatTurn, type Draft, type WorldRef } from './api'
import { JobProgress } from './JobProgress'

/** The brainstorm chat for the open world. It only proposes drafts; "Draft it" sends one to the approval queue. */
export function ChatPane({ world, town }: { world: WorldRef; town: string }) {
  const client = useQueryClient()
  const key = ['chat', JSON.stringify(world)]
  const turns = useQuery({ queryKey: key, queryFn: () => sendJson<ChatTurn[]>('/api/chat', 'POST', world) })
  const [message, setMessage] = useState('')
  const end = useRef<HTMLDivElement>(null)
  const say = useMutation({
    mutationFn: (text: string) => sendJson<ChatTurn[]>('/api/chat/say', 'POST', { ...world, message: text, town: town || null }),
    onSuccess: (next) => { client.setQueryData(key, next); setMessage('') },
  })
  const clear = useMutation({ mutationFn: () => sendJson<ChatTurn[]>('/api/chat/clear', 'POST', world), onSuccess: (next) => client.setQueryData(key, next) })
  const [drafted, setDrafted] = useState<Record<string, boolean>>({})
  const draft = useMutation({
    mutationFn: (proposal: ChatTurn['proposals'][number]) => sendJson<Draft>('/api/drafts', 'POST', { ...world, ...proposal }),
    onSuccess: async (_, proposal) => {
      setDrafted((all) => ({ ...all, [JSON.stringify(proposal)]: true }))
      await client.invalidateQueries({ queryKey: ['drafts', JSON.stringify(world)] })
    },
  })
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }) }, [turns.data?.length, say.isPending])
  return (
    <div className="chat">
      <div className="turns" aria-live="polite">
        {!turns.data?.length && <p className="muted small">Talk an idea through: a feud, a festival, who really owns the mill. When it's ready, ask for a draft.</p>}
        {turns.data?.map((turn) => (
          <div key={turn.id} className={`turn ${turn.role}`}>
            <p>{turn.text}</p>
            {turn.proposals.map((proposal) => {
              const id = JSON.stringify(proposal)
              return (
                <div key={id} className="proposal">
                  <span className="small"><strong>{proposal.target.replace(/_/g, ' ')}</strong> for {proposal.town}: {proposal.ask}</span>
                  <button type="button" disabled={draft.isPending || drafted[id]} onClick={() => draft.mutate(proposal)}>
                    <Sparkles size={13} aria-hidden /> {drafted[id] ? 'Drafted' : draft.isPending && draft.variables === proposal ? 'Drafting…' : 'Draft it'}
                  </button>
                  {draft.isPending && draft.variables === proposal && <JobProgress world={world} job="draft" compact />}
                </div>
              )
            })}
          </div>
        ))}
        {say.isPending && <div className="turn assistant"><p className="muted">Thinking…</p></div>}
        <div ref={end} />
      </div>
      {(say.isError || draft.isError) && <p className="error small">{(say.error ?? draft.error)?.message}</p>}
      <form onSubmit={(event) => { event.preventDefault(); if (message.trim()) say.mutate(message) }}>
        <textarea aria-label="Message" rows={2} placeholder={town ? `Brainstorm about ${town}…` : 'Brainstorm about this world…'} value={message}
          onChange={(event) => setMessage(event.target.value)} disabled={say.isPending}
          onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); if (message.trim()) say.mutate(message) } }} />
        <div className="chat-buttons">
          <button type="submit" disabled={say.isPending || !message.trim()} aria-label="Send"><Send size={14} aria-hidden /></button>
          <button type="button" disabled={!turns.data?.length || clear.isPending} aria-label="Clear the chat" title="Clear the chat" onClick={() => clear.mutate()}><Trash2 size={14} aria-hidden /></button>
        </div>
      </form>
    </div>
  )
}
