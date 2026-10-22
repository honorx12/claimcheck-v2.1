import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Banner } from '../components/Banner'
import { BillTable, PolicyCards } from '../components/Evidence'
import { keyOf, VERDICTS, VerdictBadge } from '../components/VerdictBadge'
import { ApiError, deleteDoc, getClaim } from '../lib/api'
import { inr } from '../lib/format'
import type { Claim } from '../lib/types'
import { NotFound } from './NotFound'

const h2 = 'text-lg font-semibold mb-2'

export function ClaimResult() {
  const { id = '' } = useParams()
  const [c, setC] = useState<Claim | null>(null)
  const [missing, setMissing] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    getClaim(id).then(setC).catch((e) => { if (e instanceof ApiError && e.status === 404) setMissing(true); else setMsg('We could not load this claim.') })
  }, [id])

  async function del() {
    if (!c || !confirm('Delete the uploaded documents? The verdict stays, the quoted evidence is removed.')) return
    try {
      await Promise.all([c.policy_id, c.bill_id].filter(Boolean).map((d) => deleteDoc(d as string)))
      setC(await getClaim(id))
    } catch { setMsg('We could not delete the documents. Please try again.') }
  }

  if (missing) return <NotFound />            // same page for "not yours" and "does not exist"
  if (msg) return <p role="alert">{msg}</p>
  if (!c || !c.result) return <div className="grid gap-3" aria-busy="true"><div className="skeleton h-12" /><div className="skeleton h-40" /></div>

  const r = c.result
  const v = VERDICTS[keyOf(c.verdict)]
  const calculable = r.estimated_eligible_amount != null
  const hasDocs = !!(c.policy_id || c.bill_id)

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_20rem] items-start">
      <div className="grid gap-6 min-w-0">
        <Banner />
        <section aria-labelledby="verdict" className="grid gap-2">
          <h1 id="verdict" className="sr-only">Result</h1>
          <div><VerdictBadge verdict={c.verdict} large /></div>
          <p>{v.text}</p>
          {c.human_review_required && <p className="text-sm text-muted">This case is flagged for human review.</p>}
        </section>
        <section aria-labelledby="why"><h2 id="why" className={h2}>Why</h2><p>{r.reason}</p></section>

        {c.scrubbed && <p className="text-sm text-muted">The documents were deleted, so the quoted evidence was removed.</p>}

        {!!r.policy_evidence?.length && <section><h2 className={h2}>Policy evidence</h2><PolicyCards items={r.policy_evidence} /></section>}
        {!!r.bill_evidence?.length && <section><h2 className={h2}>Bill lines</h2><BillTable items={r.bill_evidence} /></section>}

        {r.missing_documents.length > 0 && (
          <section><h2 className={h2}>Documents needed</h2>
            <ul className="list-disc pl-6">{r.missing_documents.map((d, i) => <li key={i}>{d}</li>)}</ul>
          </section>
        )}
        {r.limitations.length > 0 && (
          <section><h2 className={h2}>Limitations</h2>
            <ul className="list-disc pl-6">{r.limitations.map((d, i) => <li key={i}>{d}</li>)}</ul>
          </section>
        )}

        <div className="flex gap-3 flex-wrap">
          <Link to="/new" className="min-h-11 inline-flex items-center rounded-lg bg-primary text-white font-semibold px-4">New claim</Link>
          {hasDocs && <button onClick={del} className="min-h-11 rounded-lg border border-line bg-surface px-4 font-semibold">Delete documents</button>}
        </div>
      </div>

      <aside aria-label="Summary" className="lg:sticky lg:top-4 rounded-lg border border-line bg-surface p-4 grid gap-3">
        <VerdictBadge verdict={c.verdict} />
        {r.claimed_amount != null && (
          calculable ? (
            <dl className="grid gap-2">
              <div><dt className="text-sm text-muted">Claimed</dt><dd className="font-mono text-right">{inr(r.claimed_amount)}</dd></div>
              <div><dt className="text-sm text-muted">Estimated eligible</dt><dd className="font-mono text-right">{inr(r.estimated_eligible_amount)}</dd></div>
              <div><dt className="text-sm text-muted">Estimated not eligible</dt><dd className="font-mono text-right">{inr(r.estimated_non_eligible_amount)}</dd></div>
            </dl>
          ) : <p className="text-sm text-muted">Not calculable from the evidence supplied.</p>
        )}
        {r.claimed_amount == null && <p className="text-sm text-muted">Not calculable from the evidence supplied.</p>}
      </aside>
    </div>
  )
}
