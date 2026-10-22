"""Files -> pages of text -> policy clause chunks / verified bill lines.

Rules: magic bytes decide file type (never the client header). Bill lines are kept only if
their source_text AND amount appear in the page text. Flags are codes, never document text.
"""
import io
import os
import re
import threading
from decimal import Decimal, InvalidOperation

import pymupdf
import pytesseract
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from . import llm, repo, storage
from .config import settings
from .redact import redact
from .rules import norm

os.environ.setdefault("OMP_THREAD_LIMIT", "1")   # 1 thread per OCR run; OCR semaphore bounds parallel runs
Image.MAX_IMAGE_PIXELS = 25_000_000              # PIL rejects images over 2x this (decompression bomb)
OCR = threading.BoundedSemaphore(2)
OCR_CFG = "--psm 6"
LOW_CONF = 0.8

# "3.1 Text", "3.1. Text", "3) Text". A bare "30 days..." is not a clause start (Guide 14.1).
CLAUSE = re.compile(r"^\s*(\d+(?:\.\d+)+\.?|\d+[.)])\s+\S", re.M)


class ParseError(Exception):
    pass


# ---------- file type ----------
def sniff(data: bytes) -> str | None:
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    return None


MIME = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg"}


# ---------- text extraction ----------
def ocr_page(img: Image.Image) -> tuple[str, float]:
    with OCR:
        text = pytesseract.image_to_string(img, config=OCR_CFG)
        data = pytesseract.image_to_data(img, config=OCR_CFG, output_type=pytesseract.Output.DICT)
    confs = [float(c) for c in data["conf"] if float(c) >= 0]
    return text, (sum(confs) / len(confs) / 100 if confs else 0.0)


def _pdf_page_text(page) -> tuple[str, float]:
    t = page.get_text()
    if len(t.strip()) > 20:
        return t, 1.0                                   # real text layer: no OCR
    img = Image.open(io.BytesIO(page.get_pixmap(dpi=300).tobytes("png")))
    return ocr_page(img)


def extract_pages(data: bytes, ext: str, max_pages: int | None = None) -> list[tuple[int, str, float]]:
    max_pages = settings.MAX_PAGES if max_pages is None else max_pages
    if ext == "pdf":
        pdf = pymupdf.open(stream=data, filetype="pdf")
        if pdf.page_count > max_pages:
            raise ParseError("TooManyPages")
        return [(i + 1, *_pdf_page_text(p)) for i, p in enumerate(pdf)]
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
        raise ParseError("UnreadableImage")
    return [(1, *ocr_page(img))]


# ---------- policy ----------
def split_clauses(text: str):
    idx = [m.start() for m in CLAUSE.finditer(text)]
    if not idx or idx[0] != 0:
        idx.insert(0, 0)
    for a, b in zip(idx, idx[1:] + [len(text)]):
        s = text[a:b].strip()
        if s:
            m = CLAUSE.match(s)
            yield (m.group(1).rstrip(".)") if m else None), s


def policy_rows(pages) -> list[dict]:
    return [{"page": n, "clause_id": cid, "content": c, "ocr_conf": conf}
            for n, text, conf in pages for cid, c in split_clauses(text)]


# ---------- bill ----------
class Item(BaseModel):
    item: str = Field(min_length=1, max_length=200)
    quantity: Decimal = Decimal(1)
    unit_price: Decimal | None = None
    amount: Decimal
    source_text: str = Field(min_length=1, max_length=400)


class Bill(BaseModel):
    items: list[Item] = Field(max_length=200)
    total: Decimal | None = None


BILL_SYS = ("Extract hospital bill line items from the OCR text. source_text must be copied verbatim "
            "from the text. Do not correct, guess or compute amounts. "
            "total = printed grand total if visible, else null.")


def _numbers(s: str) -> set[Decimal]:
    out = set()
    for m in re.findall(r"\d[\d,]*(?:\.\d+)?", s):
        try:
            out.add(Decimal(m.replace(",", "")))
        except InvalidOperation:
            pass
    return out


def structure_bill(pages, jc=None) -> tuple[list[dict], list[str], Decimal | None]:
    """LLM structures each page; code keeps only lines proven by the source text."""
    jc = jc or llm.json_call
    items, flags, total = [], [], None
    for n, text, conf in pages:
        text = redact(text)                              # BEFORE the LLM and BEFORE the verbatim check
        b = jc(BILL_SYS, llm.sandbox("ocr", text), Bill)
        for it in b.items:
            ok = (norm(it.source_text) in norm(text)
                  and it.amount > 0 and it.quantity > 0
                  and it.amount in _numbers(it.source_text))
            if not ok:
                flags.append("line_dropped_unverified")
                continue
            items.append({"page": n, "item": it.item, "quantity": it.quantity, "unit_price": it.unit_price,
                          "amount": it.amount, "currency": "INR", "source_text": it.source_text,
                          "ocr_conf": conf})
        total = b.total if b.total is not None else total
    flags = sorted(set(flags))
    if not items:
        flags.append("no_items")
    elif total is not None and sum((i["amount"] for i in items), Decimal(0)) != total:
        flags.append("total_mismatch")                   # flag, never auto-correct
    if any(i["ocr_conf"] < LOW_CONF for i in items):
        flags.append("low_ocr_conf")
    return items, flags, total


# ---------- orchestration (runs in a background task) ----------
def run(doc: dict) -> None:
    from .retrieve import embed                          # lazy: heavy import
    uid, did = doc["user_id"], doc["id"]
    repo.set_status(did, "processing")
    try:
        data = storage.get(doc["object_key"])
        pages = extract_pages(data, doc["ext"])
        flags: list[str] = []
        if doc["kind"] == "policy":
            rows = policy_rows(pages)
            if not rows:
                raise ParseError("NoText")
            for r, v in zip(rows, embed([r["content"] for r in rows])):
                r["embedding"] = v
            repo.insert_chunks(uid, did, rows)
            if any(p[2] < LOW_CONF for p in pages):
                flags.append("low_ocr_conf")
        else:
            items, flags, _ = structure_bill(pages)
            if items:
                repo.insert_bill_items(uid, did, items)
        repo.set_status(did, "ready", page_count=len(pages), flags=flags)
    except Exception as e:
        # exception type only. Never log or store document text (NFR-3).
        repo.set_status(did, "failed", error=type(e).__name__)
