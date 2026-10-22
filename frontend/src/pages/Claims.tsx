import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Flag } from 'lucide-react'
import { VerdictBadge } from '../components/VerdictBadge'
import { listClaims } from '../lib/api'
import { when } from '../lib/format'
import type { Claim } from '../lib/types'

export function Claims() {
  const [rows, setRows] = useState<Claim[] | null>(null)
  const [err, setErr] = useState(false)
  useEffect(() => { listClaims().then(setRows).catch(() => setErr(true)) }, [])

  if (err) return <p role="alert">We couldn't load your claims. Please try again.</p>
  if (!rows) return <div className="grid gap-3" aria-busy="true">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16" />)}</div>
  return (
    <div className="grid gap-4">
      <h1 className="text-2xl font-semibold">Your claims</h1>
      {rows.length === 0 ? (
        <div className="grid gap-3 justify-start">
          <p>No claims yet.</p>
          <Link to="/new" className="min-h-11 inline-flex items-center rounded-lg bg-primary text-white font-semibold px-4">Start a claim check</Link>
        </div>
      ) : (
        <ul className="grid gap-3">
          {rows.map((c) => (
            <li key={c.id}>
              <Link to={`/claims/${c.id}`} className="flex items-center justify-between gap-3 flex-wrap rounded-lg border border-line bg-surface p-4 min-h-11">
                <span className="min-w-0">
                  <span className="block text-sm text-muted">{when(c.created_at)}</span>
                  <span className="block truncate max-w-[60vw]">{c.question}</span>
                </span>
                <span className="flex items-center gap-2">
                  {c.human_review_required && <Flag size={16} aria-label="Flagged for human review" />}
                  <VerdictBadge verdict={c.verdict} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
