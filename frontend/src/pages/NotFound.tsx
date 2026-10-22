import { Link } from 'react-router-dom'

export function NotFound() {
  return (
    <div className="grid gap-3 justify-start">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <Link to="/" className="underline min-h-11 inline-flex items-center">Go home</Link>
    </div>
  )
}
