-- ClaimCheck schema for Neon Postgres + pgvector.
-- Access model: ONLY the FastAPI backend connects (one role). Browser never touches the DB.
-- Isolation: every query filters user_id (enforced in app/repo.py, tested in tests/test_repo_sql.py).
-- No document text in audit_events, trace or error.

create extension if not exists vector;

create table if not exists documents (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  kind text not null check (kind in ('policy','bill')),
  object_key text not null unique,
  filename text not null,
  ext text not null check (ext in ('pdf','png','jpg')),
  size_bytes bigint not null,
  page_count int,
  status text not null default 'uploaded'
    check (status in ('uploaded','processing','ready','failed')),
  error text,                                   -- exception type only
  flags jsonb not null default '[]',            -- codes: total_mismatch, low_ocr_conf, ...
  created_at timestamptz not null default now(),
  processed_at timestamptz,
  delete_after timestamptz not null default (now() + interval '30 days')  -- placeholder N: decide with counsel
);
create index if not exists documents_user_idx on documents (user_id, created_at desc);
create index if not exists documents_retention_idx on documents (delete_after);
create index if not exists documents_status_idx on documents (status, created_at);

create table if not exists policy_chunks (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  document_id uuid not null references documents(id) on delete cascade,
  page int not null,
  clause_id text,
  content text not null,
  ocr_conf real not null default 1,
  embedding vector(384) not null,                -- BAAI/bge-small-en-v1.5
  fts tsvector generated always as (to_tsvector('english', content)) stored
);
create index if not exists chunks_hnsw on policy_chunks using hnsw (embedding vector_cosine_ops);
create index if not exists chunks_fts on policy_chunks using gin (fts);
create index if not exists chunks_doc on policy_chunks (user_id, document_id);

create table if not exists bill_items (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  document_id uuid not null references documents(id) on delete cascade,
  page int not null,
  item text not null,
  quantity numeric not null default 1 check (quantity > 0),
  unit_price numeric,
  amount numeric not null check (amount > 0),
  currency text not null default 'INR',
  source_text text not null,
  ocr_conf real not null default 1
);
create index if not exists items_doc on bill_items (user_id, document_id);

create table if not exists claims (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  policy_id uuid references documents(id) on delete set null,
  bill_id uuid references documents(id) on delete set null,
  question text not null check (char_length(question) between 1 and 500),
  verdict text check (verdict in ('covered','partially_covered','not_covered','documents_missing')),
  human_review_required boolean not null default false,
  result jsonb not null,                         -- validated verdict object
  trace jsonb not null default '[]',             -- CRAG steps: attempt, query terms count, flags. No document text.
  model_id text,
  llm_calls int,
  duration_ms int,
  scrubbed_at timestamptz,                       -- set when evidence removed after document deletion
  created_at timestamptz not null default now()
);
create index if not exists claims_user_idx on claims (user_id, created_at desc);
create index if not exists claims_review_idx on claims (created_at) where human_review_required;

create table if not exists reviewers (
  user_id text primary key,
  added_at timestamptz not null default now()
);

create table if not exists claim_reviews (
  id uuid primary key default gen_random_uuid(),
  claim_id uuid not null references claims(id) on delete cascade,
  reviewer_id text not null,
  outcome text not null check (outcome in ('agree','disagree','needs_more_info')),
  notes text check (char_length(notes) <= 2000),
  created_at timestamptz not null default now()
);
create index if not exists reviews_claim on claim_reviews (claim_id);

create table if not exists audit_events (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(),
  actor text,
  action text not null,                          -- document.upload, claim.analyze, review.view, ...
  target_type text,
  target_id uuid,
  meta jsonb not null default '{}'               -- counts, status codes. Never document text.
);
create index if not exists audit_actor on audit_events (actor, at desc);

-- Hardening: run as owner, then connect the app with a role that has only DML.
-- create role claimcheck_app login password '<set-in-neon-console>';
-- grant select, insert, update, delete on all tables in schema public to claimcheck_app;
-- grant usage, select on all sequences in schema public to claimcheck_app;
-- revoke create on schema public from claimcheck_app;
