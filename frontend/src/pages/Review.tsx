import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ShieldAlert } from 'lucide-react'
import { BillTable, PolicyCards } from '../components/Evidence'
import { VerdictBadge } from '../components/VerdictBadge'
import { ApiError, reviewQueue, reviewSubmit, reviewView } from '../lib/api'
import { when } from '../lib/format'
import type { Claim } from '../lib/types'

// Reviewer screens (P1). Role is enforced by the API (403), this UI only hides links.
function useLoad<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [err, setErr] = useState<number | null>(null)
  useEffect(() => { fn().then(setData).catch((e) => setErr(e instanceof ApiError ? e.status : 0)) }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  return { data, err }
}

export function ReviewQueue() {
  const { data, err } = useLoad(reviewQueue, [])
  if (err === 403) return <p role="alert">You do not have access to this page.</p>
  if (err !== null) return <p role="alert">We couldn't load the queue.</p>
  if (!data) return <div className="skeleton h-24" aria-busy="true" />
  return (
    <div className="grid gap-4">
      <h1 className="text-2xl font-semibold">Review queue</h1>
      {data.length === 0 ? <p>Nothing to review.</p> : (
        <ul className="grid gap-3">
          {data.map((c) => (
            <li key={c.id}>
              <Link to={`/review/${c.id}`} className="flex justify-between gap-3 flex-wrap rounded-lg border border-line bg-surface p-4 min-h-11">
                <span><span className="block text-sm text-muted">{when(c.created_at)}</span><span className="block truncate max-w-[60vw]">{c.question}</span></span>
                <VerdictBadge verdict={c.verdict} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function Review() {
  const { id = '' } = useParams()
  const go = useNavigate()
  const { data: c, err } = useLoad<Claim>(() => reviewView(id), [id])
  const [outcome, setOutcome] = useState<'agree' | 'disagree' | 'needs_more_info'>('agree')
  const [notes, setNotes] = useState('')
  const [msg, setMsg] = useState('')

  if (err === 403) return <p role="alert">You do not have access to this page.</p>
  if (err !== null) return <p role="alert">We couldn't load this claim.</p>
  if (!c?.result) return <div className="skeleton h-40" aria-busy="true" />
  const r = c.result

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    try { await reviewSubmit(id, outcome, notes); go('/review') } catch { setMsg('We could not save your decision. Please try again.') }
  }

  return (
    <div className="grid gap-6">
      <div role="note" className="flex gap-2 items-start rounded-lg border border-[#92400E] bg-[#FEF3C7] p-3 text-[#92400E]">
        <ShieldAlert size={18} className="shrink-0 mt-0.5" aria-hidden="true" />
        <p>You are viewing another user's document. This view is logged.</p>
      </div>
      <VerdictBadge verdict={c.verdict} large />
      <p className="text-muted">Question: {c.question}</p>
      <p>{r.reason}</p>
      {r.limitations.length > 0 && <ul className="list-disc pl-6">{r.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>}
      {!!r.policy_evidence?.length && <PolicyCards items={r.policy_evidence} />}
      {!!r.bill_evidence?.length && <BillTable items={r.bill_evidence} />}
      <form onSubmit={submit} className="grid gap-3 max-w-xl">
        <label htmlFor="outcome" className="font-semibold">Outcome</label>
        <select id="outcome" value={outcome} onChange={(e) => setOutcome(e.target.value as typeof outcome)} className="min-h-11 rounded-lg border border-line bg-surface px-3">
          <option value="agree">Agree with the assessment</option>
          <option value="disagree">Disagree</option>
          <option value="needs_more_info">Needs more information</option>
        </select>
        <label htmlFor="notes" className="font-semibold">Notes</label>
        <textarea id="notes" rows={4} maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} className="rounded-lg border border-line bg-surface px-3 py-2" />
        {msg && <p role="alert" className="text-[#991B1B]">{msg}</p>}
        <button className="min-h-11 rounded-lg bg-primary text-white font-semibold">Submit decision</button>
      </form>
    </div>
  )
}
