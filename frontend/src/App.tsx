import { useEffect, useState } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Hero } from './components/Backdrops'
import { Layout } from './components/Layout'
import { me } from './lib/api'
import { getToken } from './lib/auth'
import { ClaimResult } from './pages/ClaimResult'
import { Claims } from './pages/Claims'
import { Legal } from './pages/Legal'
import { Login } from './pages/Login'
import { NewClaim } from './pages/NewClaim'
import { NotFound } from './pages/NotFound'
import { Review, ReviewQueue } from './pages/Review'

// Route guard is a convenience only. The server decides (SEC-15).
function Guard({ authed, children }: { authed: boolean | null; children: React.ReactNode }) {
  const loc = useLocation()
  if (authed === null) return <div className="skeleton h-12" aria-busy="true" />
  return authed ? <>{children}</> : <Navigate to="/login" replace state={{ from: loc.pathname }} />
}

function Home({ authed }: { authed: boolean | null }) {
  if (authed) return <Navigate to="/new" replace />
  return (
    <Hero>
      <h1 className="text-3xl sm:text-4xl font-semibold">Will this hospital bill be paid?</h1>
      <p className="mt-4 text-white/90">Upload your health-insurance policy and the bill. ClaimCheck shows a verdict with the exact policy clause and bill lines behind it, or tells you it cannot be sure.</p>
      <div className="mt-8 flex gap-3 flex-wrap justify-center">
        <Link to="/signup" className="min-h-11 inline-flex items-center rounded-lg bg-white text-primary font-semibold px-5">Create account</Link>
        <Link to="/login" className="min-h-11 inline-flex items-center rounded-lg border border-white/60 bg-white/10 text-white font-semibold px-5">Sign in</Link>
      </div>
    </Hero>
  )
}

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null)
  const [reviewer, setReviewer] = useState(false)
  useEffect(() => {
    getToken().then((t) => {
      setAuthed(!!t)
      if (t) me().then((m) => setReviewer(m.reviewer)).catch(() => setReviewer(false))
    })
  }, [])
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout authed={!!authed} reviewer={reviewer} />}>
          <Route path="/" element={<Home authed={authed} />} />
          <Route path="/login" element={<Login mode="login" />} />
          <Route path="/signup" element={<Login mode="signup" />} />
          <Route path="/new" element={<Guard authed={authed}><NewClaim /></Guard>} />
          <Route path="/claims" element={<Guard authed={authed}><Claims /></Guard>} />
          <Route path="/claims/:id" element={<Guard authed={authed}><ClaimResult /></Guard>} />
          <Route path="/review" element={<Guard authed={authed}><ReviewQueue /></Guard>} />
          <Route path="/review/:id" element={<Guard authed={authed}><Review /></Guard>} />
          <Route path="/privacy" element={<Legal kind="privacy" />} />
          <Route path="/terms" element={<Legal kind="terms" />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
