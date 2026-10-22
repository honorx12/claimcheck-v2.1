# ClaimCheck

Upload a health-insurance policy PDF + a hospital bill, ask a question. Get one of four verdicts
(covered / partially covered / not covered / documents missing) or "needs human review", each backed
by a **quoted policy clause** and the **bill lines** used. Never invents clauses, lines or amounts.
Preliminary decision support only. Not a binding insurer decision.

```
frontend/  React + Vite + TS + Tailwind        backend/  FastAPI (Python 3.12)
docs/      Spec Pack (PRD/TRD/UX/Plan) + Build Guide
```

## Stack (updated)
| Layer | Choice |
|---|---|
| DB | Neon Postgres + pgvector (384-d HNSW) + FTS. psycopg3 pool, parameterised SQL only |
| Auth | Neon Auth, JWT verified in backend via JWKS |
| Files | S3-compatible private bucket (boto3) |
| Embeddings | `BAAI/bge-small-en-v1.5` via fastembed (CPU) |
| LLM | NVIDIA Nemotron, OpenAI-compatible HTTP via `httpx` (no SDK, no agent framework) |
| OCR | PyMuPDF text layer, Tesseract fallback |

## Pipeline
`upload -> sniff magic bytes -> store -> background parse` (policy: clause chunks + embeddings; bill: LLM
structures, code keeps only lines whose text **and** amount appear in the OCR text, PII redacted first)
`-> analyze: hybrid search (vector + OR-ed keywords, RRF) -> grade -> rewrite/retry (max 2) -> extract rules
-> reject any rule whose quote is not verbatim in a retrieved chunk on that page -> Decimal math -> verdict`.
The LLM has no tools and never calculates.

## Run
```bash
# backend
sudo apt install tesseract-ocr
cd backend && python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # fill in values
psql "$DATABASE_URL" -f schema.sql
python -m scripts.make_fixtures && pytest
uvicorn app.main:app --reload   # dev only

# integration (optional, needs Postgres with pgvector)
TEST_DATABASE_URL=postgresql://user:pw@localhost/db pytest tests/integration

# frontend
cd frontend && cp .env.example .env && npm install && npm run dev
```
Prod: `ENV=prod` (disables `/docs`, `/openapi.json`), no `--reload`, secrets from host secret store.
Schedule `python -m scripts.retention` (purge expired docs, fail stuck ones).
Then create a DML-only DB role (see bottom of `schema.sql`) and use it in `DATABASE_URL`.

## API
`GET /health` · `GET /me` · `POST /documents` (multipart `kind`,`file`) · `GET|DELETE /documents/{id}` ·
`POST /claims/analyze` · `GET /claims` · `GET /claims/{id}` · reviewer: `GET /reviews/queue`,
`GET|POST /reviews/{claim_id}` (role = row in `reviewers`, every access audit-logged).
Errors: `{"error":{"code","message","request_id"}}`, never a traceback. Other users' ids return 404.

## Deliberate differences from the Spec Pack
1. **Neon + S3 instead of Supabase.** No RLS: only the backend touches the DB, every query filters `user_id`.
   Browser uploads go through `POST /documents` (magic-byte check) instead of straight to storage.
2. **No verified rule => no verdict.** TRD maps this to "covered, amounts unadjusted". That would say "covered"
   when we only found nothing excluded. We return needs-human-review and hide amounts (matches PRD US-6).
3. Plain `httpx` for the LLM, own bounded retry (no openai/tenacity).
4. Retrieval merges chunks across CRAG attempts so earlier evidence stays citeable.

## NOT verified (read before trusting)
- 75 unit tests pass offline (LLM, DB, S3 mocked). 8 integration tests pass on real Postgres 16 + pgvector 0.6
  (`TEST_DATABASE_URL=... pytest tests/integration`: schema, hybrid search, user isolation, scrub-on-delete,
  retention). **Not run against**: real Nemotron, an actual Neon project, a real bucket, Docker build.
  Run a scratch end-to-end before sharing.
- Neon Auth endpoints in `frontend/src/lib/auth.ts` follow Better Auth defaults, unverified. Change only that file.
- NVIDIA model id has no default: copy it exactly from build.nvidia.com. Check JSON reliability on 2 model ids.
- `hnsw.iterative_scan` needs pgvector >= 0.8 (silently skipped otherwise).
- Rate limit counts finished claims, so parallel requests can slip past by a few.
- Not built yet: reviewer MFA, table-aware parsing, eval set (30+), legal text (placeholder pages).
- Limits (10 MB, 30 pages, 10/h, 30 d retention) are proposals. DPDP Act / privacy text need counsel.
- No real medical documents in git. Fixtures are synthetic.
