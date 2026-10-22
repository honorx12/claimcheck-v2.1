/**
 * Neon Auth (Better Auth) over fetch. UNVERIFIED against a live Neon Auth project:
 * endpoint paths below follow Better Auth defaults. If your project differs, change ONLY this file
 * (or swap in the official Neon Auth SDK) - the rest of the app uses signIn/signUp/signOut/getToken.
 * The JWT lives in memory only, never in localStorage. The session cookie is held by the auth host.
 */
const AUTH = import.meta.env.VITE_AUTH_URL as string

let cached: { token: string; at: number } | null = null
const TTL_MS = 4 * 60 * 1000

async function post(path: string, body: unknown) {
  const r = await fetch(`${AUTH}${path}`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  if (!r.ok) {
    // Dev only: show the real reason in the browser console. Production UI stays generic (SEC-4).
    if (import.meta.env.DEV) console.warn('[auth]', path, r.status, await r.text().catch(() => ''))
    throw new Error('auth_failed')
  }
}

export async function signIn(email: string, password: string) {
  cached = null
  await post('/sign-in/email', { email, password })
}

export async function signUp(email: string, password: string) {
  cached = null
  await post('/sign-up/email', { email, password, name: email.split('@')[0] })
}

export async function signOut() {
  cached = null
  try { await post('/sign-out', {}) } catch { /* session already gone */ }
}

/** Short-lived JWT for the API. Returns null when there is no session. */
export async function getToken(): Promise<string | null> {
  if (cached && Date.now() - cached.at < TTL_MS) return cached.token
  try {
    const r = await fetch(`${AUTH}/token`, { credentials: 'include' })
    if (!r.ok) return null
    const { token } = (await r.json()) as { token?: string }
    if (!token) return null
    cached = { token, at: Date.now() }
    return token
  } catch {
    return null
  }
}
