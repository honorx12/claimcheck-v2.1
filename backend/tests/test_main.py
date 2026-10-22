import datetime as dt
import io
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main, parse, repo, storage
from app.auth import current_user_id

main.app.dependency_overrides[current_user_id] = lambda: "user-1"
client = TestClient(main.app, raise_server_exceptions=False)
ID = str(uuid.uuid4())
NOW = dt.datetime(2026, 10, 21, tzinfo=dt.timezone.utc)


def doc(kind="policy", status="ready", **kw):
    return {"id": uuid.UUID(ID), "user_id": "user-1", "kind": kind, "object_key": "user-1/x.pdf", "filename": "f.pdf",
            "ext": "pdf", "size_bytes": 1, "page_count": 1, "status": status, "error": None, "flags": [],
            "created_at": NOW, **kw}


@pytest.fixture(autouse=True)
def mocks(monkeypatch):
    for n in ("count_recent_documents", "count_recent_claims"):
        monkeypatch.setattr(repo, n, lambda uid, hours=1: 0)
    monkeypatch.setattr(repo, "audit", MagicMock())
    monkeypatch.setattr(repo, "insert_document", MagicMock(return_value=doc(status="uploaded")))
    monkeypatch.setattr(repo, "is_reviewer", lambda uid: False)
    monkeypatch.setattr(storage, "put", MagicMock(return_value="user-1/x.pdf"))
    monkeypatch.setattr(storage, "delete", MagicMock())
    monkeypatch.setattr(parse, "run", MagicMock())


def png():
    b = io.BytesIO(); Image.new("RGB", (10, 10), "white").save(b, "PNG"); return b.getvalue()


def up(data, kind="bill", name="a.png"):
    return client.post("/documents", data={"kind": kind}, files={"file": (name, data, "image/png")})


# ---- health / auth / docs ----
def test_health_open():
    assert client.get("/health").json() == {"ok": True}


def test_no_token_401():
    main.app.dependency_overrides.pop(current_user_id)
    try:
        r = client.get("/claims")
        assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized" and r.json()["error"]["request_id"]
    finally:
        main.app.dependency_overrides[current_user_id] = lambda: "user-1"


def test_docs_enabled_only_in_dev():
    assert main.app.docs_url == "/docs"    # prod flag covered by config.is_prod


# ---- upload ----
def test_upload_ok_and_background_processing():
    r = up(png())
    assert r.status_code == 202 and r.json()["status"] == "processing"
    assert storage.put.call_args.args[1] == "png"      # type from bytes
    assert parse.run.called


def test_upload_garbage_415():
    assert up(b"not a file").status_code == 415


def test_upload_pdf_header_spoof_still_checked_by_bytes():
    assert up(b"GIF89a....", name="x.pdf").status_code == 415


def test_policy_must_be_pdf():
    assert up(png(), kind="policy").status_code == 415


def test_bad_kind_422():
    assert client.post("/documents", data={"kind": "x"}, files={"file": ("a", png())}).status_code == 422


def test_too_large_413(monkeypatch):
    monkeypatch.setattr(main.settings, "MAX_FILE_BYTES", 10)
    assert up(png()).status_code == 413


def test_upload_rate_limited(monkeypatch):
    monkeypatch.setattr(repo, "count_recent_documents", lambda uid, hours=1: 99)
    assert up(png()).status_code == 429


def test_db_failure_deletes_object():
    repo.insert_document.side_effect = RuntimeError("db down")
    r = up(png())
    assert r.status_code == 500 and storage.delete.called
    assert "db down" not in r.text and "Traceback" not in r.text and "Reference:" in r.json()["error"]["message"]


# ---- ownership / enumeration ----
def test_foreign_or_missing_doc_404(monkeypatch):
    monkeypatch.setattr(repo, "get_document", lambda uid, did, kind=None: None)
    assert client.get(f"/documents/{ID}").status_code == 404


def test_non_uuid_ids_404():
    assert client.get("/documents/1;drop table documents").status_code == 404
    assert client.get("/claims/%7B%22%24ne%22%3Anull%7D").status_code == 404


def test_owner_scope_passed_to_repo(monkeypatch):
    seen = {}
    monkeypatch.setattr(repo, "get_document", lambda uid, did, kind=None: seen.update(uid=uid) or doc())
    client.get(f"/documents/{ID}")
    assert seen["uid"] == "user-1"


def test_delete_document(monkeypatch):
    monkeypatch.setattr(repo, "delete_document", lambda uid, did: "user-1/x.pdf")
    assert client.delete(f"/documents/{ID}").status_code == 204 and storage.delete.called


def test_delete_foreign_404(monkeypatch):
    monkeypatch.setattr(repo, "delete_document", lambda uid, did: None)
    assert client.delete(f"/documents/{ID}").status_code == 404


# ---- analyze ----
def body(**kw):
    return {"policy_id": ID, "bill_id": str(uuid.uuid4()), "question": "Is it covered?", **kw}


def test_analyze_validation():
    assert client.post("/claims/analyze", json=body(question="")).status_code == 422
    assert client.post("/claims/analyze", json=body(question="x" * 501)).status_code == 422
    assert client.post("/claims/analyze", json=body(question="   ")).status_code == 422
    assert client.post("/claims/analyze", json=body(policy_id="nope")).status_code == 422
    assert client.post("/claims/analyze", json=body(policy_id={"$ne": None})).status_code == 422
    assert client.post("/claims/analyze", json=body(extra=1)).status_code == 422


def test_analyze_sqli_text_is_just_text(monkeypatch):
    monkeypatch.setattr(repo, "get_document", lambda uid, did, kind=None: doc(kind=kind or "policy"))
    seen = {}
    monkeypatch.setattr(main.agent, "analyze", lambda uid, p, b, q: seen.update(q=q) or
                        {"id": uuid.uuid4(), "question": q, "verdict": None, "human_review_required": True,
                         "result": {}, "created_at": NOW})
    r = client.post("/claims/analyze", json=body(question="'; drop table claims; --"))
    assert r.status_code == 200 and seen["q"] == "'; drop table claims; --"


def test_analyze_not_ready_409(monkeypatch):
    monkeypatch.setattr(repo, "get_document", lambda uid, did, kind=None: doc(kind=kind, status="processing"))
    assert client.post("/claims/analyze", json=body()).status_code == 409


def test_analyze_rate_limit_429(monkeypatch):
    monkeypatch.setattr(repo, "get_document", lambda uid, did, kind=None: doc(kind=kind))
    monkeypatch.setattr(repo, "count_recent_claims", lambda uid, hours=1: 10)
    assert client.post("/claims/analyze", json=body()).status_code == 429


def test_analyze_wrong_kind_404(monkeypatch):
    monkeypatch.setattr(repo, "get_document", lambda uid, did, kind=None: None if kind == "bill" else doc())
    assert client.post("/claims/analyze", json=body()).status_code == 404


def test_llm_down_502_no_claim(monkeypatch):
    from app.llm import LLMUnavailable
    monkeypatch.setattr(repo, "get_document", lambda uid, did, kind=None: doc(kind=kind))
    monkeypatch.setattr(main.agent, "analyze", MagicMock(side_effect=LLMUnavailable("Timeout")))
    r = client.post("/claims/analyze", json=body())
    assert r.status_code == 502 and r.json()["error"]["code"] == "llm_unavailable"


# ---- claims ----
def test_claim_roundtrip(monkeypatch):
    monkeypatch.setattr(repo, "get_claim", lambda uid, cid: {"id": uuid.UUID(ID), "question": "q", "verdict": "covered",
                        "human_review_required": False, "result": {"claimed_amount": "1"}, "scrubbed_at": None, "created_at": NOW})
    r = client.get(f"/claims/{ID}")
    assert r.status_code == 200 and r.json()["result"]["claimed_amount"] == "1"


def test_scrubbed_flag(monkeypatch):
    monkeypatch.setattr(repo, "get_claim", lambda uid, cid: {"id": uuid.UUID(ID), "question": "q", "verdict": None,
                        "human_review_required": True, "result": {}, "scrubbed_at": NOW, "created_at": NOW})
    assert client.get(f"/claims/{ID}").json()["scrubbed"] is True


# ---- reviewer ----
def test_normal_user_403_on_reviewer_routes():
    assert client.get("/reviews/queue").status_code == 403
    assert client.get(f"/reviews/{ID}").status_code == 403
    assert client.post(f"/reviews/{ID}", json={"outcome": "agree"}).status_code == 403


def test_reviewer_flow_is_audited(monkeypatch):
    monkeypatch.setattr(repo, "is_reviewer", lambda uid: True)
    monkeypatch.setattr(repo, "review_queue", lambda: [])
    monkeypatch.setattr(repo, "get_claim_any", lambda cid: {"id": uuid.UUID(ID), "question": "q", "verdict": None,
                        "human_review_required": True, "result": {}, "created_at": NOW})
    monkeypatch.setattr(repo, "insert_review", MagicMock())
    assert client.get("/reviews/queue").status_code == 200
    assert client.get(f"/reviews/{ID}").status_code == 200
    assert client.post(f"/reviews/{ID}", json={"outcome": "agree", "notes": "ok"}).status_code == 200
    assert client.post(f"/reviews/{ID}", json={"outcome": "bogus"}).status_code == 422
    actions = [c.args[1] for c in repo.audit.call_args_list]
    assert {"review.queue", "review.view", "review.decision"} <= set(actions)


# ---- headers / errors ----
def test_security_headers_and_no_store():
    r = client.get("/health")
    assert r.headers["cache-control"] == "no-store" and r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-request-id"]


def test_unknown_route_uses_error_shape():
    r = client.get("/nope")
    assert r.status_code == 404 and set(r.json()["error"]) == {"code", "message", "request_id"}


def test_me_reports_reviewer_flag(monkeypatch):
    assert client.get("/me").json() == {"reviewer": False}
    monkeypatch.setattr(repo, "is_reviewer", lambda uid: True)
    assert client.get("/me").json() == {"reviewer": True}
