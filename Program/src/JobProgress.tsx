import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { sendJson, type WorldRef } from './api'

export type Job = 'world' | 'town' | 'draft' | 'cast'
interface Progress {
  running: boolean; step?: string; index?: number; of?: number; label?: string; attempt?: number; about?: string
  started?: string; step_started?: string; problems?: string[]
}

function since(start: string | undefined, now: number): string {
  if (!start) return ''
  const seconds = Math.max(0, Math.round((now - Date.parse(start)) / 1000))
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s`
}

/** While the model works on a world, a town or one list: the step it is on, which try, and how long it has taken.
 * `queue` says where this one sits in a run of several ("Town 2 of 5"). */
export function JobProgress({ world, job, queue, compact }: { world: WorldRef; job: Job; queue?: string; compact?: boolean }) {
  const progress = useQuery({
    queryKey: ['progress', job, JSON.stringify(world)], refetchInterval: 1500, gcTime: 0,
    queryFn: () => sendJson<Progress>('/api/progress', 'POST', { ...world, job }),
  })
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer) }, [])
  const step = progress.data
  if (!step?.running || !step.index || !step.of) return <p className="muted small" role="status">{queue ? `${queue}: ` : ''}Starting…</p>
  const retry = !!step.attempt && step.attempt > 1
  return (
    <div className="draft-steps" role="status" aria-live="polite">
      <div className="draft-bar" role="progressbar" aria-valuemin={0} aria-valuemax={step.of} aria-valuenow={step.index - 1}
        aria-label={step.about ? `Drafting ${step.about}` : 'Drafting'}>
        <span style={{ width: `${((step.index - 0.5) / step.of) * 100}%` }} />
      </div>
      <p className="small">
        {queue && <strong>{queue}{step.about ? `, ${step.about}` : ''}. </strong>}
        Step {step.index} of {step.of}: {step.label}{retry ? ' (second try)' : ''}…
        <span className="muted"> {since(step.step_started, now)} on this step, {since(step.started, now)} in all.</span>
      </p>
      {retry && !!step.problems?.length && <p className="muted small">The first try was sent back: {step.problems.join('; ')}</p>}
      {!compact && <p className="muted small">Each writing step is one call to the model and can take a minute or two. The timer keeps counting while it works.</p>}
    </div>
  )
}
