export type Verdict = 'covered' | 'partially_covered' | 'not_covered' | 'documents_missing' | null

export interface PolicyEvidence { kind: string; value: string | null; applies_to: string | null; clause_id: string | null; page: number; quote: string }
export interface BillEvidence { item: string; quantity: string; amount: string; page: number; source_text: string; eligible?: string }

export interface ClaimResult {
  verdict: Verdict
  human_review_required: boolean
  reason: string
  currency: string
  claimed_amount: string | null
  estimated_eligible_amount: string | null
  estimated_non_eligible_amount: string | null
  policy_evidence?: PolicyEvidence[]
  bill_evidence?: BillEvidence[]
  missing_documents: string[]
  limitations: string[]
}

export interface Claim {
  id: string
  question: string
  verdict: Verdict
  human_review_required: boolean
  created_at: string
  result?: ClaimResult
  policy_id?: string
  bill_id?: string
  scrubbed?: boolean
}

export interface Doc { id: string; kind: 'policy' | 'bill'; status: 'uploaded' | 'processing' | 'ready' | 'failed'; error: string | null; flags: string[] }
