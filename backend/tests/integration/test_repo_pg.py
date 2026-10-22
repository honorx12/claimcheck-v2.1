"""Real-Postgres checks for app/repo.py. Skipped unless TEST_DATABASE_URL is set (schema.sql applied).
    TEST_DATABASE_URL=postgresql://cc:cc@localhost/cc pytest tests/integration
"""
import os
import random
import uuid
from decimal import Decimal as D

import pytest

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

if URL:
    os.environ["DATABASE_URL"] = URL
    from app import repo
    from app.db import pool


@pytest.fixture(scope="module", autouse=True)
def _pool():
    pool.open()
    yield
    pool.close()


def vec(seed):
    r = random.Random(seed)
    return [r.random() for _ in range(384)]


def mkdoc(uid, kind="policy"):
    return repo.insert_document(uid, kind, f"{uid}/{uuid.uuid4()}.pdf", "f.pdf", "pdf", 10, 30)


def test_document_scoped_by_user():
    a, b = f"a-{uuid.uuid4()}", f"b-{uuid.uuid4()}"
    d = mkdoc(a)
    assert repo.get_document(a, d["id"])["status"] == "uploaded"
    assert repo.get_document(b, d["id"]) is None                  # other user: nothing
    assert repo.get_document(a, d["id"], "bill") is None          # wrong kind
    repo.set_status(d["id"], "ready", page_count=3, flags=["low_ocr_conf"])
    g = repo.get_document(a, d["id"])
    assert g["status"] == "ready" and g["page_count"] == 3 and g["flags"] == ["low_ocr_conf"]


def test_hybrid_search_isolated_and_ranked():
    a, b = f"a-{uuid.uuid4()}", f"b-{uuid.uuid4()}"
    da, db_ = mkdoc(a), mkdoc(b)
    rows = [{"page": 1, "clause_id": "3.1", "content": "Room rent is covered up to Rs 5000 per day.", "ocr_conf": 1, "embedding": vec(1)},
            {"page": 1, "clause_id": "5.1", "content": "Cosmetic procedures are excluded.", "ocr_conf": 1, "embedding": vec(2)}]
    repo.insert_chunks(a, da["id"], rows)
    repo.insert_chunks(b, db_["id"], [{**rows[0], "content": "SECRET of user b room rent"}])
    hits = repo.search_chunks(a, da["id"], "cosmetic or room", vec(2), 8)
    assert hits[0]["clause_id"] == "5.1" and len(hits) == 2          # vec(2)+keyword agree
    assert all("SECRET" not in h["content"] for h in hits)
    assert repo.search_chunks(a, db_["id"], "room", vec(1), 8) == []   # a cannot search b's doc


def test_search_injection_text_is_inert():
    a = f"a-{uuid.uuid4()}"
    d = mkdoc(a)
    repo.insert_chunks(a, d["id"], [{"page": 1, "clause_id": None, "content": "x", "ocr_conf": 1, "embedding": vec(3)}])
    repo.search_chunks(a, d["id"], "'); drop table claims; --", vec(3), 8)
    repo.get_claim(a, str(uuid.uuid4()))                              # table still there


def test_bill_items_decimal_roundtrip():
    a = f"a-{uuid.uuid4()}"
    d = mkdoc(a, "bill")
    repo.insert_bill_items(a, d["id"], [{"page": 1, "item": "Room", "quantity": D("2"), "amount": D("12000.10"),
                                         "source_text": "Room Rs 12,000.10", "ocr_conf": 0.9}])
    it = repo.get_bill_items(a, d["id"])[0]
    assert it["amount"] == D("12000.10") and it["quantity"] == D("2")


def test_claim_insert_list_get_scoped_and_rate_count():
    a, b = f"a-{uuid.uuid4()}", f"b-{uuid.uuid4()}"
    p, bl = mkdoc(a), mkdoc(a, "bill")
    out = {"verdict": "covered", "human_review_required": False, "policy_evidence": [{"quote": "q"}], "bill_evidence": [{"item": "x"}]}
    row = repo.insert_claim(a, p["id"], bl["id"], "q?", out, [{"attempt": 0}], "m", 3, 10)
    assert repo.get_claim(a, row["id"])["verdict"] == "covered"
    assert repo.get_claim(b, row["id"]) is None
    assert [c["id"] for c in repo.list_claims(a)] == [row["id"]] and repo.list_claims(b) == []
    assert repo.count_recent_claims(a) == 1 and repo.count_recent_claims(b) == 0


def test_delete_scrubs_evidence_keeps_verdict_and_cascades():
    a = f"a-{uuid.uuid4()}"
    p, bl = mkdoc(a), mkdoc(a, "bill")
    repo.insert_chunks(a, p["id"], [{"page": 1, "clause_id": "1", "content": "c", "ocr_conf": 1, "embedding": vec(4)}])
    out = {"verdict": "partially_covered", "human_review_required": False, "claimed_amount": "100",
           "policy_evidence": [{"quote": "q"}], "bill_evidence": [{"item": "x"}]}
    row = repo.insert_claim(a, p["id"], bl["id"], "q", out, [], "m", 1, 1)
    assert repo.delete_document(f"other-{uuid.uuid4()}", p["id"]) is None      # not yours
    assert repo.delete_document(a, p["id"]).endswith(".pdf")
    c = repo.get_claim(a, row["id"])
    assert c["scrubbed_at"] and c["verdict"] == "partially_covered" and c["result"]["claimed_amount"] == "100"
    assert "policy_evidence" not in c["result"] and "bill_evidence" not in c["result"]
    assert c["policy_id"] is None and repo.search_chunks(a, p["id"], "c", vec(4), 8) == []


def test_review_queue_and_audit():
    a, rv = f"a-{uuid.uuid4()}", f"r-{uuid.uuid4()}"
    p, bl = mkdoc(a), mkdoc(a, "bill")
    row = repo.insert_claim(a, p["id"], bl["id"], "q", {"verdict": None, "human_review_required": True}, [], "m", 0, 0)
    assert str(row["id"]) in [str(c["id"]) for c in repo.review_queue(500)]
    assert not repo.is_reviewer(rv)
    repo.insert_review(row["id"], rv, "agree", None)
    assert str(row["id"]) not in [str(c["id"]) for c in repo.review_queue(500)]
    repo.audit(rv, "review.decision", "claim", row["id"], {"outcome": "agree"})


def test_reap_stale_and_expired():
    a = f"a-{uuid.uuid4()}"
    d = mkdoc(a)
    with pool.connection() as c:
        c.execute("update documents set created_at = now() - interval '1 hour', delete_after = now() - interval '1 day' where id=%s", (d["id"],))
    assert repo.reap_stale(10) >= 1
    assert repo.get_document(a, d["id"])["error"] == "Timeout"
    assert str(d["id"]) in [str(x["id"]) for x in repo.expired_documents(1000)]
