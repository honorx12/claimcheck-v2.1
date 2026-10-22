import { AlertTriangle, CheckCircle2, FileQuestion, UserCheck, XCircle } from 'lucide-react'
import type { Verdict } from '../lib/types'

export const VERDICTS = {
  covered: { label: 'Covered', fg: '#166534', bg: '#DCFCE7', Icon: CheckCircle2, text: 'Based on the clauses below, this bill appears payable.' },
  partially_covered: { label: 'Partially covered', fg: '#92400E', bg: '#FEF3C7', Icon: AlertTriangle, text: 'Part of this bill appears payable. See what reduces it.' },
  not_covered: { label: 'Not covered', fg: '#991B1B', bg: '#FEE2E2', Icon: XCircle, text: 'A clause below appears to exclude this bill.' },
  documents_missing: { label: 'Documents missing', fg: '#1E40AF', bg: '#DBEAFE', Icon: FileQuestion, text: 'We need more documents to decide.' },
  review: { label: 'Needs human review', fg: '#3F3F46', bg: '#E4E4E7', Icon: UserCheck, text: "We couldn't reach a reliable conclusion." },
} as const

export const keyOf = (v: Verdict) => (v ?? 'review') as keyof typeof VERDICTS

export function VerdictBadge({ verdict, large }: { verdict: Verdict; large?: boolean }) {
  const { label, fg, bg, Icon } = VERDICTS[keyOf(verdict)]
  return (
    <span style={{ color: fg, background: bg }}
      className={`inline-flex items-center gap-2 rounded-full font-semibold ${large ? 'px-4 py-2 text-lg' : 'px-3 py-1 text-sm'}`}>
      <Icon size={large ? 22 : 16} aria-hidden="true" />{label}
    </span>
  )
}
