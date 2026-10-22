# ClaimCheck setup guide

Time: ~45 min first run. Order matters.

## 0. Prereqs
Python 3.12, Node 22, git, `psql`, Tesseract (`sudo apt install tesseract-ocr` / `brew install tesseract`).

## 1. Neon (DB + Auth)
1. neon.tech -> new project. Region near your API host.
2. Connection string: copy the **pooled** one (host has `-pooler`). Keep `?sslmode=require`.
3. Enable **Neon Auth** for the project. Copy two URLs from its console page:
   - base URL -> `NEON_AUTH_BASE_URL`
   - JWKS URL (`.../.well-known/jwks.json`) -> `NEON_AUTH_JWKS_URL`
   (Exact paths differ by Neon version. Use what the console shows.)
4. Schema (owner connection string): `psql "$DATABASE_URL" -f backend/schema.sql`
5. App role (recommended). In Neon SQL editor:
   ```sql
   create role claimcheck_app login password 'CHANGE_ME';
   grant select, insert, update, delete on all tables in schema public to claimcheck_app;
   revoke create on schema public from claimcheck_app;
   ```
   Use this role's pooled connection string as `DATABASE_URL` in the app.

## 2. Bucket (private, S3-compatible)
R2 / S3 / Backblaze all work.
1. New bucket `claim-docs`, **private**, no public URL.
2. API key with read/write on that bucket only.
3. Fill `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`, `AWS_REGION` (`auto` for R2).
No browser CORS needed: uploads go through the backend.

## 3. NVIDIA
build.nvidia.com -> pick a Nemotron model -> create API key (`nvapi-...`).
`NVIDIA_MODEL` = the exact model id shown on the model page. No default on purpose.
Read NVIDIA data terms before real users (health data leaves your system).

## 4. Backend
```bash
cd backend
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # fill every value from steps 1-3
python -m scripts.make_fixtures
pytest                          # 75 pass
uvicorn app.main:app --reload --port 8000
curl localhost:8000/health      # {"ok":true}
```
First real upload downloads the embedding model (~130 MB). Be patient once.

Optional DB tests (any Postgres with pgvector, schema applied):
`TEST_DATABASE_URL=postgresql://... pytest tests/integration`

## 5. Frontend
```bash
cd frontend
cp .env.example .env     # VITE_API=http://localhost:8000, VITE_AUTH_URL=<Neon Auth base URL>
npm install
npm run dev              # http://localhost:5173
```
`backend/.env` -> `FRONTEND_ORIGIN=http://localhost:5173` (CORS).

If sign-in fails: `frontend/src/lib/auth.ts` assumes Better Auth paths
(`/sign-in/email`, `/sign-up/email`, `/token`, `/sign-out`). Check Neon Auth docs, edit that one file.

## 6. Smoke test
1. Sign up, confirm email (if enabled), sign in.
2. `/new`: policy `backend/tests/fixtures/02_partial_policy.pdf`, bill `bill_ok.png`.
3. Question: "Will this bill be paid? What will I owe?"
4. Expect: verdict + quoted clauses (3.1 room cap, 4.1 co-pay) + bill lines. Wrong/odd result?
   Check `trace` column in `claims` and try another NVIDIA model id.
5. Try `05_injection_policy.pdf`: verdict must not become "covered" from the injected text.

## 7. Make yourself a reviewer
Get your user id (JWT `sub`, or Neon Auth users table), then:
```sql
insert into reviewers (user_id) values ('<your-sub>');
```
Reload app: "Review" appears in nav.

## 8. Deploy
**API (Render/Railway/Fly, Docker, root = `backend/`)**
- Env: everything in `.env.example`, plus `ENV=prod`, `FRONTEND_ORIGIN=https://your-frontend`.
- Pick a plan with >= 1 GB RAM (embedding model + OCR).
- Cron job daily: `python -m scripts.retention`.

**Frontend (Vercel/Netlify, root = `frontend/`)**
- Env: `VITE_API`, `VITE_AUTH_URL`. Build `npm run build`, output `dist`.
- Edit `vercel.json` CSP: replace `YOUR-API-HOST` with your API host.

## 9. Pre-share security checks (all must pass)
```bash
curl -i https://API/docs            # 404
curl -i https://API/openapi.json    # 404
curl -i https://API/.env            # 404
curl -i https://FRONT/.env          # 404 (or SPA html, never secrets)
curl -i https://API/claims          # 401
gitleaks detect                     # clean, incl. history
grep -rEl 'nvapi-|AWS_SECRET|DATABASE_URL' frontend/dist   # no output
```
Then with two real accounts: user B opens user A's `/claims/<id>` -> same 404 page as a missing claim.

## 10. Troubleshooting
| Symptom | Fix |
|---|---|
| App won't start, validation error | missing env var. Required: DB, Neon Auth x2, S3 x3, NVIDIA x2 |
| 401 on every call | JWKS URL wrong, or token issuer/audience differ from `NEON_AUTH_BASE_URL` origin (`app/auth.py`) |
| 502 on analyze | LLM failed 3 tries. Check key, model id, quota |
| Doc stuck `processing` | check logs for exception type. Reaper fails it after 10 min |
| Doc `failed` / `TooManyPages` | file over 30 pages. Raise `MAX_PAGES` or split |
| Blurry bill, odd amounts | expected: low OCR flag -> human review. Use clearer scan/PDF |
| DB timeout at first request | Neon waking from scale-to-zero. Retry |
| Slow first upload | embedding model downloading once |
