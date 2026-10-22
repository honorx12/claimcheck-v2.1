"""Mask identifiers BEFORE text goes to the third-party LLM (Build Guide 15.2)."""
import re

PII = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)"), "[PHONE]"),
    (re.compile(r"(?<!\d)\d{12}(?!\d)"), "[ID12]"),           # Aadhaar-length ids. Amounts stay (<9 digits)
]


def redact(t: str) -> str:
    for rx, tag in PII:
        t = rx.sub(tag, t)
    return t
