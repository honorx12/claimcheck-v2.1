import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Banner } from '../components/Banner'
import { Steps, type StepState } from '../components/Steps'
import { analyze, ApiError, getDoc, MAX_BYTES, uploadDoc } from '../lib/api'

const MAX_Q = 500
const input = 'min-h-11 w-full rounded-lg border border-line bg-surface px-3 py-2'
const LABELS = ['Uploading', 'Reading documents', 'Searching policy', 'Checking evidence']
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

async function waitReady(id: string) {              // poll every 2 s, give up after 3 min
  for (let i = 0; i < 90; i++) {
    const d = await getDoc(id)
    if (d.status === 'ready') return
    if (d.status === 'failed') throw new Error('unreadable')
    await sleep(2000)
  }
  throw new Error('timeout')
}

function fileError(f: File | null, kind: 'policy' | 'bill'): string {
  if (!f) return ''
  if (f.size > MAX_BYTES) return 'This file is over 10 MB. Try a smaller scan.'
  const ok = kind === 'policy' ? ['application/pdf'] : ['application/pdf', 'image/png', 'image/jpeg']
  return ok.includes(f.type) ? '' : kind === 'policy' ? 'Policy must be a PDF.' : 'Bill must be a PDF, PNG or JPEG.'
}

function message(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 429) return "You've reached the hourly limit. Please try again later."
    if (e.status === 401) return 'Your session expired. Please sign in again.'
    if (e.status === 502) return 'Analysis is unavailable right now. Try again in a few minutes.'
    if (e.status === 415 || e.status === 413) return e.message
    return e.requestId ? `Something went wrong. Reference: ${e.requestId}` : e.message
  }
  if (e instanceof Error && e.message === 'unreadable') return "We couldn't read this file. Try a clearer scan or a PDF."
  if (e instanceof Error && e.message === 'timeout') return 'This is taking longer than usual. Please try again.'
  return 'Something went wrong. Please try again.'
}

export function NewClaim() {
  const [policy, setPolicy] = useState<File | null>(null)
  const [bill, setBill] = useState<File | null>(null)
  const [q, setQ] = useState('')
  const [step, setStep] = useState(-1)                 // -1 idle, 0..3 working
  const [err, setErr] = useState('')
  const go = useNavigate()

  const pErr = fileError(policy, 'policy'), bErr = fileError(bill, 'bill')
  const qOk = q.trim().length >= 1 && q.length <= MAX_Q
  const ready = !!policy && !!bill && !pErr && !bErr && qOk && step < 0

  async function run() {
    if (!policy || !bill) return
    setErr(''); setStep(0)
    try {
      const [p, b] = await Promise.all([uploadDoc(policy, 'policy'), uploadDoc(bill, 'bill')])
      setStep(1)
      await Promise.all([waitReady(p.id), waitReady(b.id)])
      setStep(2)
      const pending = analyze(p.id, b.id, q.trim())
      setTimeout(() => setStep((s) => (s === 2 ? 3 : s)), 1500)   // cosmetic: server does both in one call
      const claim = await pending
      go(`/claims/${claim.id}`)
    } catch (e) {
      setErr(message(e)); setStep(-1)
    }
  }

  const steps = LABELS.map((label, i) => ({
    label, state: (step < 0 ? 'todo' : i < step ? 'done' : i === step ? 'working' : 'todo') as StepState,
  }))

  return (
    <div className="grid gap-5 max-w-2xl">
      <h1 className="text-2xl font-semibold">New claim check</h1>
      <Banner />
      <div>
        <label htmlFor="policy" className="block mb-1 font-semibold">Policy document (PDF)</label>
        <input id="policy" type="file" accept="application/pdf" className={input} aria-describedby={pErr ? 'policy-err' : undefined}
          onChange={(e) => setPolicy(e.target.files?.[0] ?? null)} />
        {policy && !pErr && <p className="text-sm text-muted mt-1">{policy.name} · {(policy.size / 1048576).toFixed(1)} MB</p>}
        {pErr && <p id="policy-err" role="alert" className="text-[#991B1B] text-sm mt-1">{pErr}</p>}
      </div>
      <div>
        <label htmlFor="bill" className="block mb-1 font-semibold">Hospital bill (PDF, PNG or JPEG)</label>
        <input id="bill" type="file" accept="application/pdf,image/png,image/jpeg" className={input} aria-describedby={bErr ? 'bill-err' : undefined}
          onChange={(e) => setBill(e.target.files?.[0] ?? null)} />
        {bill && !bErr && <p className="text-sm text-muted mt-1">{bill.name} · {(bill.size / 1048576).toFixed(1)} MB</p>}
        {bErr && <p id="bill-err" role="alert" className="text-[#991B1B] text-sm mt-1">{bErr}</p>}
      </div>
      <div>
        <label htmlFor="q" className="block mb-1 font-semibold">Your question</label>
        <textarea id="q" rows={3} maxLength={MAX_Q} className={input} value={q} onChange={(e) => setQ(e.target.value)} aria-describedby="q-hint" />
        <p id="q-hint" className="text-sm text-muted mt-1">{q.length}/{MAX_Q} · Example: Will this bill be paid? What will I owe?</p>
      </div>
      <p className="text-sm text-muted">
        Your documents contain health information. They are stored privately in your account. Text from them is sent to an AI
        service to analyse them. You can delete them at any time.
      </p>
      {err && <p role="alert" className="text-[#991B1B]">{err}</p>}
      <button onClick={run} disabled={!ready} className="min-h-11 rounded-lg bg-primary text-white font-semibold disabled:opacity-50">
        Analyse
      </button>
      {step >= 0 && <Steps steps={steps} />}
    </div>
  )
}
