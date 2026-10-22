// PLACEHOLDER. Privacy policy and terms must be drafted with counsel, not by the model (Spec Pack, UX 3.6).
export function Legal({ kind }: { kind: 'privacy' | 'terms' }) {
  return (
    <div className="grid gap-3 max-w-2xl">
      <h1 className="text-2xl font-semibold">{kind === 'privacy' ? 'Privacy policy' : 'Terms of use'}</h1>
      <p>This text has not been written yet. It must be reviewed by a qualified professional before real users upload documents.</p>
      <p className="text-sm text-muted">ClaimCheck gives a preliminary assessment only. Your insurer makes the final decision.</p>
    </div>
  )
}
