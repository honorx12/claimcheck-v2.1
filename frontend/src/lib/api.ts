import { getToken } from './auth'
import type { Claim, Doc } from './types'

const API = import.meta.env.VITE_API as string

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public requestId?: string) { super(message) }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await getToken()
  if (!token) throw new ApiError(401, 'unauthorized', 'Please sign in again.')
  const r = await fetch(`${API}${path}`, { ...init, headers: { ...(init.headers ?? {}), Authorization: `Bearer ${token}` } })
  if (r.status === 204) return undefined as T
  const body = await r.json().catch(() => null)
  if (!r.ok) {
    const e = body?.error
    throw new ApiError(r.status, e?.code ?? 'error', e?.message ?? 'Something went wrong.', e?.request_id)
  }
  return body as T
}

export const uploadDoc = (file: File, kind: 'policy' | 'bill') => {
  const fd = new FormData(); fd.append('kind', kind); fd.append('file', file)
  return call<{ id: string }>('/documents', { method: 'POST', body: fd })
}
export const getDoc = (id: string) => call<Doc>(`/documents/${id}`)
export const deleteDoc = (id: string) => call<void>(`/documents/${id}`, { method: 'DELETE' })
export const analyze = (policy_id: string, bill_id: string, question: string) =>
  call<Claim>('/claims/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ policy_id, bill_id, question }) })
export const listClaims = () => call<Claim[]>('/claims')
export const getClaim = (id: string) => call<Claim>(`/claims/${id}`)

export const MAX_BYTES = 10 * 1024 * 1024

export const me = () => call<{ reviewer: boolean }>('/me')
export const reviewQueue = () => call<Claim[]>('/reviews/queue')
export const reviewView = (id: string) => call<Claim>(`/reviews/${id}`)
export const reviewSubmit = (id: string, outcome: 'agree' | 'disagree' | 'needs_more_info', notes: string) =>
  call<{ ok: boolean }>(`/reviews/${id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ outcome, notes }) })
