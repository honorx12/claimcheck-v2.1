// Display only. All money math happens on the server with Decimal.
export const inr = (v: string | null | undefined) =>
  v == null ? '' : new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(Number(v))
export const when = (iso: string) => new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
