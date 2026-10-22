"""CRAG pipeline: retrieve -> grade -> (rewrite -> retrieve) x N -> extract rules -> validate quotes
-> Decimal calc -> verdict. Bounded retries, then abstain. The LLM never calculates and never
sees a tool. Verdict mapping follows TRD section 5 (one deliberate deviation, see README)."""
import time
from decimal import Decimal
from typing import Callable

from pydantic import BaseModel, Field

from . import llm, repo
from .config import settings
from .parse import LOW_CONF
from .retrieve import search
from .rules import Rule, calc, validate_citations, verdict as map_verdict

BANNER = "Preliminary assessment. Not a binding insurer decision."
LIMITATION_TEXT = {
    "low_ocr_conf": "Low OCR confidence: some text may be misread.",
    "total_mismatch": "Printed total differs from the sum of lines.",
    "line_dropped_unverified": "Some lines could not be verified against the document and were ignored.",
    "no_verified_rule": "No policy rule could be verified from the clauses, so amounts are not calculable.",
}
MAX_EVIDENCE = 10


class Grade(BaseModel):
    relevant: bool
    sufficient: bool                         # enough to decide? separate from relevant
    missing: str = Field("", max_length=300)  # concept still needed, for query rewrite
    missing_docs: list[str] = Field(default_factory=list, max_length=10)


class Rules(BaseModel):
    rules: list[Rule] = Field(default_factory=list, max_length=20)


class Q(BaseModel):
    query: str = Field(max_length=300)


def fmt(ev: list[dict]) -> str:
    return "\n".join(llm.sandbox("clause", e["content"], id=e.get("clause_id") or "none", page=e["page"])
                     for e in ev)


def _grade(jc, question, names, ev) -> Grade:
    return jc("Grade the clauses. relevant = they discuss the topic. sufficient = the clauses together with "
              "the bill items are enough to decide coverage (not merely on-topic). Name the missing concept "
              "and any missing documents (e.g. policy schedule, discharge summary).",
              f"{llm.sandbox('question', question)}\n{llm.sandbox('bill', names)}\n{fmt(ev)}", Grade)


def _rewrite(jc, question, missing) -> str:
    return jc("Write one short alternative search query for the missing concept.",
              f"{llm.sandbox('question', question)}\nMissing concept: {llm.sandbox('data', missing)}", Q).query


def _extract(jc, names, ev) -> list[Rule]:
    return jc("Extract applicable rules ONLY if stated in the clauses. kind is one of: exclusion, copay_pct, "
              "room_rent_cap_per_day (value = rupees per day), room_rent_proportionate. "
              "quote = exact words copied from one clause. page = that clause's page. "
              "Do not infer. Do not compute.",
              f"{llm.sandbox('bill', names)}\n{fmt(ev)}", Rules).rules


def _merge(pool: dict, new: list[dict]) -> list[dict]:
    for e in new:
        pool.setdefault(str(e["id"]), e)
    return sorted(pool.values(), key=lambda e: -float(e.get("score", 0)))[:MAX_EVIDENCE]


def analyze(uid: str, policy_doc: dict, bill_doc: dict, question: str,
            search_fn: Callable = None) -> dict:
    search_fn = search_fn or search
    t0, calls = time.monotonic(), 0

    def jc(system, user, model):
        nonlocal calls
        calls += 1
        return llm.json_call(system, user, model)

    items = repo.get_bill_items(uid, bill_doc["id"])
    names = ", ".join(i["item"] for i in items)
    trace: list[dict] = []
    query, g, pool, ev = f"{question} {names}", None, {}, []

    for attempt in range(settings.CRAG_MAX_RETRIES + 1):
        if not items:
            break                                         # nothing to check: skip retrieval entirely
        ev = _merge(pool, search_fn(uid, policy_doc["id"], query))
        g = _grade(jc, question, names, ev)
        trace.append({"attempt": attempt, "chunks": len(ev), "relevant": g.relevant, "sufficient": g.sufficient})
        if g.sufficient:
            break
        if attempt < settings.CRAG_MAX_RETRIES:
            query = _rewrite(jc, question, g.missing)

    out = {"verdict": None, "human_review_required": True, "evidence_sufficient": bool(g and g.sufficient),
           "missing_documents": [], "policy_evidence": [], "bill_evidence": [], "limitations": [],
           "reason": "", "currency": "INR", "banner": BANNER,
           "claimed_amount": None, "estimated_eligible_amount": None, "estimated_non_eligible_amount": None}

    bill_flags = set(bill_doc.get("flags") or [])
    if any(float(i["ocr_conf"]) < LOW_CONF for i in items):
        bill_flags.add("low_ocr_conf")

    if not items:
        out["reason"] = "No bill lines could be extracted. A human should review this."
    elif not g.sufficient and g.missing_docs:
        out |= {"verdict": "documents_missing", "human_review_required": False,
                "missing_documents": g.missing_docs,
                "reason": "The documents provided are not enough to decide. More documents are needed."}
    elif not g.sufficient:
        out["reason"] = "We could not reach a reliable conclusion after bounded retries. A human should review this."
    else:
        rules = validate_citations(_extract(jc, names, ev), ev)
        claimed = sum((Decimal(str(i["amount"])) for i in items), Decimal(0))
        out["bill_evidence"] = [{"item": i["item"], "quantity": str(i["quantity"]), "amount": str(i["amount"]),
                                 "page": i["page"], "source_text": i["source_text"]} for i in items]
        out["claimed_amount"] = str(claimed)
        out["policy_evidence"] = [r.model_dump(mode="json") for r in rules]
        if rules:
            eligible, lines = calc(items, rules)
            out["verdict"] = map_verdict(claimed, eligible)
            out["estimated_eligible_amount"] = str(eligible)
            out["estimated_non_eligible_amount"] = str(claimed - eligible)
            for be, (_, _, ok) in zip(out["bill_evidence"], lines):
                be["eligible"] = str(ok)
            out["reason"] = "Computed by fixed rules from the policy clauses quoted below."
        else:
            bill_flags.add("no_verified_rule")
            out["reason"] = "The clauses found do not contain a rule we could verify. A human should review this."
        out["human_review_required"] = (not rules) or bool(bill_flags & {"low_ocr_conf", "total_mismatch"})

    out["limitations"] = [LIMITATION_TEXT[f] for f in sorted(bill_flags) if f in LIMITATION_TEXT]
    row = repo.insert_claim(uid, policy_doc["id"], bill_doc["id"], question, out, trace,
                            settings.NVIDIA_MODEL, calls, int((time.monotonic() - t0) * 1000))
    return row
