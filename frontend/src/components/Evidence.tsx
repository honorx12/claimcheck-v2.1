import { inr } from '../lib/format'
import type { BillEvidence, PolicyEvidence } from '../lib/types'

const chip = 'inline-block rounded-md border border-line bg-bg px-2 py-0.5 font-mono text-xs'
const RULE_TEXT: Record<string, string> = {
  exclusion: 'Excludes', copay_pct: 'Co-payment', room_rent_cap_per_day: 'Room rent cap per day',
  room_rent_proportionate: 'Proportionate deduction',
}

// All document text renders as plain text (React escapes it). Never as HTML.
export function PolicyCards({ items }: { items: PolicyEvidence[] }) {
  return (
    <ul className="grid gap-3" aria-label="Policy evidence">
      {items.map((r, i) => (
        <li key={i} className="rounded-lg border border-line bg-surface p-4">
          <div className="flex flex-wrap gap-2 mb-2">
            {r.clause_id && <span className={chip}>Clause {r.clause_id}</span>}
            <span className={chip}>Page {r.page}</span>
          </div>
          <blockquote className="font-mono text-sm whitespace-pre-wrap break-words border-l-4 border-primary pl-3">{r.quote}</blockquote>
          <p className="mt-2 text-sm text-muted">
            Supports: {RULE_TEXT[r.kind] ?? r.kind}
            {r.applies_to ? ` "${r.applies_to}"` : ''}{r.value ? ` (${r.value})` : ''}
          </p>
        </li>
      ))}
    </ul>
  )
}

export function BillTable({ items }: { items: BillEvidence[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full text-sm">
        <caption className="sr-only">Bill lines used</caption>
        <thead className="text-left text-muted">
          <tr>
            <th scope="col" className="p-3">Item</th>
            <th scope="col" className="p-3 text-right">Qty</th>
            <th scope="col" className="p-3 text-right">Amount</th>
            <th scope="col" className="p-3 text-right">Eligible</th>
            <th scope="col" className="p-3">Page</th>
            <th scope="col" className="p-3">Source text</th>
          </tr>
        </thead>
        <tbody>
          {items.map((b, i) => (
            <tr key={i} className="border-t border-line align-top">
              <td className="p-3">{b.item}</td>
              <td className="p-3 text-right font-mono">{b.quantity}</td>
              <td className="p-3 text-right font-mono">{inr(b.amount)}</td>
              <td className="p-3 text-right font-mono">{b.eligible != null ? inr(b.eligible) : '-'}</td>
              <td className="p-3 font-mono">{b.page}</td>
              <td className="p-3 font-mono text-xs break-words min-w-48">{b.source_text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
