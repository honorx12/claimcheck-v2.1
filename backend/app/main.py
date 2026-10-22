"""HTTP layer. Auth on every route except /health. Every id is a UUID, every lookup is owner-scoped,
foreign or missing ids both return 404 (no enumeration). Errors share one shape, never a traceback."""
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import agent, parse, repo, storage
from .auth import current_user_id
from .config import settings
from .db import pool
from .llm import LLMUnavailable

log = logging.getLogger("claimcheck")


@asynccontextmanager
async def lifespan(_: FastAPI):
    pool.open()
    try:
        yield
    finally:
        pool.close()


app = FastAPI(
    lifespan=lifespan,
    docs_url=None if settings.is_prod else "/docs",
    redoc_url=None if settings.is_prod else "/redoc",
    openapi_url=None if settings.is_prod else "/openapi.json",
)
app.add_middleware(CORSMiddleware, allow_origins=[settings.FRONTEND_ORIGIN], allow_credentials=False,
                   allow_methods=["GET", "POST", "DELETE"], allow_headers=["Authorization", "Content-Type"])


# ---------- errors: one shape ----------
def _err(status: int, code: str, message: str, rid: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "request_id": rid}}, status_code=status,
                        headers={"Cache-Control": "no-store"})


def _rid(request: Request) -> str:
    return getattr(request.state, "rid", "-")


CODES = {401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict", 413: "too_large",
         415: "unsupported_type", 422: "invalid_input", 429: "rate_limited", 502: "llm_unavailable",
         503: "unavailable"}
MESSAGES = {401: "Please sign in again.", 403: "Not allowed.", 404: "Not found.", 409: "Not ready yet.",
            413: "File is too large.", 415: "Unsupported file type.", 422: "Invalid input.",
            429: "You've reached the hourly limit. Please try again later.",
            502: "Analysis is unavailable right now. Try again in a few minutes.",
            503: "Service unavailable. Try again shortly."}


@app.exception_handler(StarletteHTTPException)
async def http_exc(request: Request, exc: StarletteHTTPException):
    s = exc.status_code
    return _err(s, CODES.get(s, "error"), MESSAGES.get(s, "Request failed."), _rid(request))


@app.exception_handler(RequestValidationError)
async def val_exc(request: Request, exc: RequestValidationError):
    return _err(422, "invalid_input", MESSAGES[422], _rid(request))      # never echo input back


@app.exception_handler(LLMUnavailable)
async def llm_exc(request: Request, exc: LLMUnavailable):
    log.warning("llm_unavailable rid=%s kind=%s", _rid(request), exc)
    return _err(502, "llm_unavailable", MESSAGES[502], _rid(request))


@app.exception_handler(Exception)
async def any_exc(request: Request, exc: Exception):
    log.error("unhandled rid=%s type=%s", _rid(request), type(exc).__name__)   # type only, no message/trace
    rid = _rid(request)
    return _err(500, "server_error", f"Something went wrong. Reference: {rid}", rid)


@app.middleware("http")
async def base_headers(request: Request, call_next):
    request.state.rid = uuid.uuid4().hex[:12]
    t0 = time.monotonic()
    try:
        resp = await call_next(request)
    except Exception:                                    # raised outside handlers
        rid = request.state.rid
        log.error("unhandled rid=%s", rid)
        resp = _err(500, "server_error", f"Something went wrong. Reference: {rid}", rid)
    resp.headers["X-Request-ID"] = request.state.rid
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    log.info("rid=%s %s %s %s %dms", request.state.rid, request.method, request.url.path, resp.status_code,
             int((time.monotonic() - t0) * 1000))       # no query string, no body, no user data
    return resp


# ---------- helpers ----------
def _uuid(v: str) -> str:
    try:
        return str(UUID(v))
    except (ValueError, AttributeError):
        raise HTTPException(404)


def _own(uid: str, doc_id: str, kind: str | None = None) -> dict:
    d = repo.get_document(uid, _uuid(doc_id), kind)
    if not d:
        raise HTTPException(404)                         # 404 not 403: do not reveal other users' ids
    return d


def _public_doc(d: dict) -> dict:
    return {"id": str(d["id"]), "kind": d["kind"], "filename": d["filename"], "status": d["status"],
            "error": d["error"], "flags": d["flags"], "page_count": d["page_count"],
            "created_at": d["created_at"].isoformat() if d.get("created_at") else None}


def _public_claim(c: dict) -> dict:
    out = {"id": str(c["id"]), "question": c["question"], "verdict": c["verdict"],
           "human_review_required": c["human_review_required"],
           "created_at": c["created_at"].isoformat()}
    if "result" in c:
        out["result"] = c["result"]
    for k in ("policy_id", "bill_id"):               # lets the owner delete the source documents
        if c.get(k):
            out[k] = str(c[k])
    if c.get("scrubbed_at"):
        out["scrubbed"] = True
    return out


def reviewer_id(uid: str = Depends(current_user_id)) -> str:
    if not repo.is_reviewer(uid):                        # role from DB table, never from token claims
        raise HTTPException(403)
    return uid


# ---------- routes ----------
@app.get("/health")
def health():
    return {"ok": True}


@app.get("/me")
def me(uid: str = Depends(current_user_id)):
    return {"reviewer": repo.is_reviewer(uid)}          # UI hint only. Reviewer routes re-check server-side


@app.post("/documents", status_code=202)
def upload(bg: BackgroundTasks, kind: Literal["policy", "bill"] = Form(...), file: UploadFile = File(...),
           uid: str = Depends(current_user_id)):
    if repo.count_recent_documents(uid) >= settings.UPLOADS_PER_HOUR:
        raise HTTPException(429)
    data = file.file.read(settings.MAX_FILE_BYTES + 1)
    if len(data) > settings.MAX_FILE_BYTES:
        raise HTTPException(413)
    ext = parse.sniff(data)                              # type from the bytes, not the client header
    if ext is None or (kind == "policy" and ext != "pdf"):
        raise HTTPException(415)
    name = (os.path.basename(file.filename or "") or kind).replace("\x00", "")[:120]
    key = storage.put(uid, ext, data, parse.MIME[ext])
    try:
        doc = repo.insert_document(uid, kind, key, name, ext, len(data), settings.RETENTION_DAYS)
    except Exception:
        storage.delete(key)                              # no orphan file without a row
        raise
    repo.audit(uid, "document.upload", "document", doc["id"], {"kind": kind, "bytes": len(data)})
    bg.add_task(parse.run, doc)
    return {"id": str(doc["id"]), "status": "processing"}


@app.get("/documents/{doc_id}")
def read_document(doc_id: str, uid: str = Depends(current_user_id)):
    return _public_doc(_own(uid, doc_id))


@app.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str, uid: str = Depends(current_user_id)):
    did = _uuid(doc_id)
    key = repo.delete_document(uid, did)                 # scrubs claim evidence, cascades chunks/items
    if key is None:
        raise HTTPException(404)
    storage.delete(key)
    repo.audit(uid, "document.delete", "document", did)


Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                            max_length=settings.MAX_QUESTION_CHARS)]


class Analyze(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_id: UUID
    bill_id: UUID
    question: Question


@app.post("/claims/analyze")
def analyze(body: Analyze, uid: str = Depends(current_user_id)):
    policy = _own(uid, str(body.policy_id), "policy")
    bill = _own(uid, str(body.bill_id), "bill")
    if policy["status"] != "ready" or bill["status"] != "ready":
        raise HTTPException(409)
    if repo.count_recent_claims(uid) >= settings.ANALYSES_PER_HOUR:
        raise HTTPException(429)
    row = agent.analyze(uid, policy, bill, body.question)
    repo.audit(uid, "claim.analyze", "claim", row["id"], {"verdict": row["verdict"]})
    return _public_claim(row)


@app.get("/claims")
def list_claims(uid: str = Depends(current_user_id)):
    return [_public_claim(c) for c in repo.list_claims(uid)]


@app.get("/claims/{claim_id}")
def read_claim(claim_id: str, uid: str = Depends(current_user_id)):
    c = repo.get_claim(uid, _uuid(claim_id))
    if not c:
        raise HTTPException(404)
    return _public_claim(c)


# ---------- reviewer (P1) ----------
@app.get("/reviews/queue")
def review_queue(rid: str = Depends(reviewer_id)):
    repo.audit(rid, "review.queue")
    return [_public_claim(c) for c in repo.review_queue()]


@app.get("/reviews/{claim_id}")
def review_view(claim_id: str, rid: str = Depends(reviewer_id)):
    cid = _uuid(claim_id)
    c = repo.get_claim_any(cid)
    if not c:
        raise HTTPException(404)
    repo.audit(rid, "review.view", "claim", cid)
    return _public_claim(c)


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["agree", "disagree", "needs_more_info"]
    notes: str = Field("", max_length=2000)


@app.post("/reviews/{claim_id}")
def review_submit(claim_id: str, body: Review, rid: str = Depends(reviewer_id)):
    cid = _uuid(claim_id)
    if not repo.get_claim_any(cid):
        raise HTTPException(404)
    repo.insert_review(cid, rid, body.outcome, body.notes or None)
    repo.audit(rid, "review.decision", "claim", cid, {"outcome": body.outcome})
    return {"ok": True}
