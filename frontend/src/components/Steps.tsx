import { CheckCircle2, Circle, Loader2, XCircle } from 'lucide-react'

export type StepState = 'todo' | 'working' | 'done' | 'failed'
const ICON = { todo: Circle, working: Loader2, done: CheckCircle2, failed: XCircle }
const WORD = { todo: 'waiting', working: 'working', done: 'done', failed: 'failed' }

export function Steps({ steps }: { steps: { label: string; state: StepState }[] }) {
  return (
    <ol aria-live="polite" aria-label="Progress" className="grid gap-2">
      {steps.map((s) => {
        const I = ICON[s.state]
        return (
          <li key={s.label} className="flex items-center gap-2 min-h-8">
            <I size={18} aria-hidden="true" className={s.state === 'working' ? 'animate-spin' : ''} />
            <span>{s.label}</span><span className="text-sm text-muted">({WORD[s.state]})</span>
          </li>
        )
      })}
    </ol>
  )
}
