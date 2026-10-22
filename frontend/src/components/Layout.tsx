import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { LogOut, ShieldCheck } from 'lucide-react'
import { signOut } from '../lib/auth'

const nav = 'min-h-11 inline-flex items-center px-3 rounded-lg text-sm font-semibold'

export function Layout({ authed, reviewer }: { authed: boolean; reviewer?: boolean }) {
  const go = useNavigate()
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-surface border-b border-line">
        <div className="mx-auto max-w-5xl px-4 py-2 flex items-center justify-between gap-2 flex-wrap">
          <Link to="/" className="inline-flex items-center gap-2 min-h-11 font-semibold text-primary">
            <ShieldCheck aria-hidden="true" /> ClaimCheck
          </Link>
          {authed && (
            <nav aria-label="Main" className="flex items-center gap-1">
              <NavLink to="/new" className={nav}>New claim</NavLink>
              <NavLink to="/claims" className={nav}>History</NavLink>
              {reviewer && <NavLink to="/review" className={nav}>Review</NavLink>}
              <button className={`${nav} gap-1 text-muted`} onClick={async () => { await signOut(); go('/login') }}>
                <LogOut size={16} aria-hidden="true" /> Sign out
              </button>
            </nav>
          )}
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl px-4 py-6 flex-1"><Outlet /></main>
      <footer className="border-t border-line text-sm text-muted">
        <div className="mx-auto max-w-5xl px-4 py-4 flex gap-4 flex-wrap">
          <span>Preliminary decision support only.</span>
          <Link to="/privacy" className="underline">Privacy</Link>
          <Link to="/terms" className="underline">Terms</Link>
        </div>
      </footer>
    </div>
  )
}
