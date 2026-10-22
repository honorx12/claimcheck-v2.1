"""All SQL lives here. Parameterised only (SEC-17). Every read/write is scoped by user_id (SEC-6)."""
import json
from decimal import Decimal

import psycopg

from .db import pool


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


# ---------- documents ----------
def insert_document(uid, kind, key, filename, ext, size, retention_days) -> dict:
    with pool.connection() as c:
        return c.execute(
            """insert into documents (user_id, kind, object_key, filename, ext, size_bytes, delete_after)
               values (%s,%s,%s,%s,%s,%s, now() + make_interval(days => %s))
               returning id, user_id, kind, object_key, filename, ext, status""",
            (uid, kind, key, filename, ext, size, retention_days)).fetchone()


def get_document(uid, doc_id, kind=None) -> dict | None:
    with pool.connection() as c:
        return c.execute(
            """select id, user_id, kind, object_key, filename, ext, size_bytes, page_count, status,
                      error, flags, created_at
               from documents where id=%s and user_id=%s and (%s::text is null or kind=%s)""",
            (doc_id, uid, kind, kind)).fetchone()


def set_status(doc_id, status, error=None, page_count=None, flags=None) -> None:
    with pool.connection() as c:
        c.execute(
            """update documents set status=%s, error=%s,
                 page_count=coalesce(%s, page_count),
                 flags=coalesce(%s::jsonb, flags),
                 processed_at = case when %s in ('ready','failed') then now() else processed_at end
               where id=%s""",
            (status, error, page_count, None if flags is None else json.dumps(flags), status, doc_id))


def count_recent_documents(uid, hours=1) -> int:
    with pool.connection() as c:
        return c.execute(
            "select count(*) n from documents where user_id=%s and created_at > now() - make_interval(hours => %s)",
            (uid, hours)).fetchone()["n"]


# ---------- chunks / items ----------
def insert_chunks(uid, doc_id, rows: list[dict]) -> None:
    with pool.connection() as c, c.cursor() as cur:
        cur.executemany(
            """insert into policy_chunks (user_id, document_id, page, clause_id, content, ocr_conf, embedding)
               values (%s,%s,%s,%s,%s,%s,%s::vector)""",
            [(uid, doc_id, r["page"], r["clause_id"], r["content"], r["ocr_conf"], _vec(r["embedding"]))
             for r in rows])


def insert_bill_items(uid, doc_id, rows: list[dict]) -> None:
    with pool.connection() as c, c.cursor() as cur:
        cur.executemany(
            """insert into bill_items (user_id, document_id, page, item, quantity, unit_price, amount,
                                       currency, source_text, ocr_conf)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [(uid, doc_id, r["page"], r["item"], r["quantity"], r.get("unit_price"), r["amount"],
              r.get("currency", "INR"), r["source_text"], r["ocr_conf"]) for r in rows])


def get_bill_items(uid, doc_id) -> list[dict]:
    with pool.connection() as c:
        return c.execute(
            """select item, quantity, amount, currency, page, source_text, ocr_conf
               from bill_items where user_id=%s and document_id=%s order by page, id""",
            (uid, doc_id)).fetchall()


HYBRID_SQL = """
with sem as (
  select id, row_number() over (order by embedding <=> %(emb)s::vector) r
  from policy_chunks where user_id=%(uid)s and document_id=%(doc)s
  order by embedding <=> %(emb)s::vector limit 20
), kw as (
  select p.id, row_number() over (order by ts_rank_cd(p.fts, q) desc) r
  from policy_chunks p, websearch_to_tsquery('english', %(q)s) q
  where p.user_id=%(uid)s and p.document_id=%(doc)s and p.fts @@ q
  order by ts_rank_cd(p.fts, q) desc limit 20
)
select c.id, c.page, c.clause_id, c.content, c.ocr_conf,
       coalesce(1.0/(60+sem.r),0) + coalesce(1.0/(60+kw.r),0) as score
from sem full join kw using (id)
join policy_chunks c using (id)
order by score desc limit %(k)s
"""


def search_chunks(uid, doc_id, q_or: str, emb: list[float], k=8) -> list[dict]:
    """Reciprocal-rank fusion of vector (cosine) + Postgres full-text. q_or = OR-ed safe terms."""
    with pool.connection() as c:
        try:   # pgvector >= 0.8: keep scanning the HNSW index when the user/doc filter drops rows
            with c.transaction():
                c.execute("set local hnsw.iterative_scan = relaxed_order")
        except psycopg.Error:
            pass
        return c.execute(HYBRID_SQL, {"emb": _vec(emb), "uid": uid, "doc": doc_id, "q": q_or, "k": k}).fetchall()


# ---------- claims ----------
def insert_claim(uid, policy_id, bill_id, question, out: dict, trace: list, model_id, calls, ms) -> dict:
    with pool.connection() as c:
        return c.execute(
            """insert into claims (user_id, policy_id, bill_id, question, verdict, human_review_required,
                                   result, trace, model_id, llm_calls, duration_ms)
               values (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
               returning id, question, verdict, human_review_required, result, created_at""",
            (uid, policy_id, bill_id, question, out["verdict"], out["human_review_required"],
             json.dumps(out), json.dumps(trace), model_id, calls, ms)).fetchone()


def count_recent_claims(uid, hours=1) -> int:
    with pool.connection() as c:
        return c.execute(
            "select count(*) n from claims where user_id=%s and created_at > now() - make_interval(hours => %s)",
            (uid, hours)).fetchone()["n"]


def list_claims(uid, limit=50) -> list[dict]:
    with pool.connection() as c:
        return c.execute(
            """select id, question, verdict, human_review_required, created_at
               from claims where user_id=%s order by created_at desc limit %s""", (uid, limit)).fetchall()


def get_claim(uid, claim_id) -> dict | None:
    with pool.connection() as c:
        return c.execute(
            """select id, question, verdict, human_review_required, result, scrubbed_at, created_at,
                      policy_id, bill_id
               from claims where id=%s and user_id=%s""", (claim_id, uid)).fetchone()


# ---------- delete / retention ----------
def delete_document(uid, doc_id) -> str | None:
    """Scrub evidence from claims, then delete the row (chunks/items cascade). Returns object_key."""
    with pool.connection() as c:
        row = c.execute("select object_key from documents where id=%s and user_id=%s for update",
                        (doc_id, uid)).fetchone()
        if not row:
            return None
        c.execute(
            """update claims set result = coalesce(result,'{}'::jsonb) - 'policy_evidence' - 'bill_evidence',
                                 scrubbed_at = now()
               where user_id=%s and (policy_id=%s or bill_id=%s)""", (uid, doc_id, doc_id))
        c.execute("delete from documents where id=%s and user_id=%s", (doc_id, uid))
        return row["object_key"]


def expired_documents(limit=100) -> list[dict]:
    with pool.connection() as c:
        return c.execute("select id, user_id from documents where delete_after < now() limit %s",
                         (limit,)).fetchall()


def reap_stale(minutes) -> int:
    with pool.connection() as c:
        return c.execute(
            """update documents set status='failed', error='Timeout', processed_at=now()
               where status in ('uploaded','processing') and created_at < now() - make_interval(mins => %s)""",
            (minutes,)).rowcount


# ---------- reviewers / audit ----------
def is_reviewer(uid) -> bool:
    with pool.connection() as c:
        return c.execute("select 1 from reviewers where user_id=%s", (uid,)).fetchone() is not None


def review_queue(limit=50) -> list[dict]:
    with pool.connection() as c:
        return c.execute(
            """select c.id, c.question, c.verdict, c.created_at
               from claims c
               where c.human_review_required
                 and not exists (select 1 from claim_reviews r where r.claim_id = c.id)
               order by c.created_at asc limit %s""", (limit,)).fetchall()


def get_claim_any(claim_id) -> dict | None:       # reviewer routes only
    with pool.connection() as c:
        return c.execute(
            "select id, question, verdict, human_review_required, result, created_at from claims where id=%s",
            (claim_id,)).fetchone()


def insert_review(claim_id, reviewer_id, outcome, notes) -> None:
    with pool.connection() as c:
        c.execute("insert into claim_reviews (claim_id, reviewer_id, outcome, notes) values (%s,%s,%s,%s)",
                  (claim_id, reviewer_id, outcome, notes))


def audit(actor, action, target_type=None, target_id=None, meta=None) -> None:
    with pool.connection() as c:
        c.execute(
            "insert into audit_events (actor, action, target_type, target_id, meta) values (%s,%s,%s,%s,%s::jsonb)",
            (actor, action, target_type, target_id, json.dumps(meta or {})))
