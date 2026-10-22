import { Info } from 'lucide-react'

export function Banner() {
  return (
    <div role="note" className="flex gap-2 items-start rounded-lg border border-line bg-surface p-3 text-sm text-muted">
      <Info size={18} className="shrink-0 mt-0.5" aria-hidden="true" />
      <p>Preliminary assessment based on the documents you uploaded. Your insurer makes the final decision.</p>
    </div>
  )
}
