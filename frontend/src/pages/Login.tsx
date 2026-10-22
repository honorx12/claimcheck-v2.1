import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Eye, EyeOff } from 'lucide-react'
import { AuthBackdrop } from '../components/Backdrops'
import { signIn, signUp } from '../lib/auth'

const input = 'min-h-11 w-full rounded-lg border border-line bg-surface px-3'

export function Login({ mode }: { mode: 'login' | 'signup' }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [err, setErr] = useState('')
  const [info, setInfo] = useState('')
  const [busy, setBusy] = useState(false)
  const go = useNavigate()
  const from = (useLocation().state as { from?: string } | null)?.from ?? '/new'
  const signup = mode === 'signup'

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(''); setInfo(''); setBusy(true)
    try {
      if (signup) { await signUp(email, password); setInfo('Check your email to confirm.') }
      else { await signIn(email, password); go(from, { replace: true }) }
    } catch {
      setErr(signup ? 'We could not create that account. Check the details and try again.' : 'Email or password is incorrect.')
    } finally { setBusy(false) }
  }

  return (
    <AuthBackdrop>
      <h1 className="text-2xl font-semibold mb-4">{signup ? 'Create account' : 'Sign in'}</h1>
      <form onSubmit={submit} className="grid gap-4" noValidate>
        <div>
          <label htmlFor="email" className="block mb-1 font-semibold">Email</label>
          <input id="email" type="email" autoComplete="email" required className={input} value={email}
            onChange={(e) => setEmail(e.target.value)} aria-describedby={err ? 'form-err' : undefined} />
        </div>
        <div>
          <label htmlFor="pw" className="block mb-1 font-semibold">Password</label>
          <div className="flex gap-2">
            <input id="pw" type={show ? 'text' : 'password'} autoComplete={signup ? 'new-password' : 'current-password'}
              required minLength={signup ? 10 : undefined} className={input} value={password}
              onChange={(e) => setPassword(e.target.value)} />
            <button type="button" className="min-h-11 min-w-11 grid place-items-center rounded-lg border border-line bg-surface"
              onClick={() => setShow(!show)} aria-label={show ? 'Hide password' : 'Show password'}>
              {show ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
        </div>
        {err && <p id="form-err" role="alert" className="text-[#991B1B]">{err}</p>}
        {info && <p role="status">{info}</p>}
        <button disabled={busy || !email || !password}
          className="min-h-11 rounded-lg bg-primary text-white font-semibold disabled:opacity-50">
          {busy ? 'Please wait...' : signup ? 'Create account' : 'Sign in'}
        </button>
      </form>
      <p className="mt-4 text-sm text-muted">
        {signup ? <>Have an account? <Link className="underline" to="/login">Sign in</Link></> : <>New here? <Link className="underline" to="/signup">Create account</Link></>}
        {' '}· <Link className="underline" to="/privacy">Privacy</Link> · <Link className="underline" to="/terms">Terms</Link>
      </p>
    </AuthBackdrop>
  )
}
