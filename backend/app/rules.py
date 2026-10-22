"""Money math + citation check. No LLM here: amounts come from Decimal only."""
import re
from decimal import Decimal as D, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, model_validator

# shortcut: real policies define "associated expenses" in the clause. Hardcoded exempt list here.
EXEMPT = ("pharmacy", "medicine", "drug", "implant", "consumable")


class Rule(BaseModel):
    kind: Literal["exclusion", "copay_pct", "room_rent_cap_per_day", "room_rent_proportionate"]
    value: D | None = None
    applies_to: str | None = None    # bill-item keyword, for exclusions
    clause_id: str | None = None
    page: int
    quote: str                       # verbatim from the clause

    @model_validator(mode="after")
    def _complete(self):
        if self.kind == "copay_pct" and (self.value is None or not 0 <= self.value <= 100):
            raise ValueError("copay_pct needs a value 0..100")
        if self.kind == "room_rent_cap_per_day" and (self.value is None or self.value <= 0):
            raise ValueError("room_rent_cap_per_day needs a value > 0")
        if self.kind == "exclusion" and not (self.applies_to or "").strip():
            raise ValueError("exclusion needs applies_to")
        return self


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def validate_citations(rules: list[Rule], ev: list[dict]) -> list[Rule]:
    """Keep only rules whose quote appears verbatim in a retrieved chunk of the same page."""
    return [r for r in rules
            if r.quote.strip()
            and any(e["page"] == r.page and norm(r.quote) in norm(e["content"]) for e in ev)]


def calc(items: list[dict], rules: list[Rule]) -> tuple[D, list[tuple]]:
    """items: dicts with item, quantity, amount. Returns (eligible_total, [(name, claimed, eligible)]).
    Order: exclusion -> room cap / proportionate cut -> co-pay on the total."""
    copay = next((r.value for r in rules if r.kind == "copay_pct"), D(0))
    cap = next((r.value for r in rules if r.kind == "room_rent_cap_per_day"), None)
    prop = any(r.kind == "room_rent_proportionate" for r in rules)
    excl = [r.applies_to.lower() for r in rules if r.kind == "exclusion" and r.applies_to]
    room = next((i for i in items if "room" in i["item"].lower()), None)

    ratio = D(1)
    if cap is not None and room:
        days = D(str(room["quantity"])) or D(1)
        per_day = D(str(room["amount"])) / days
        if per_day > cap:
            ratio = cap / per_day

    total, lines = D(0), []
    for it in items:
        amt, name = D(str(it["amount"])), it["item"].lower()
        ok = D(0) if any(e in name for e in excl) else amt
        if it is room:
            if cap is not None:
                ok = min(ok, cap * (D(str(it["quantity"])) or D(1)))
        elif prop and not any(x in name for x in EXEMPT):
            ok *= ratio
        total += ok
        lines.append((it["item"], amt, ok))
    eligible = (total * (D(100) - copay) / D(100)).quantize(D("0.01"), ROUND_HALF_UP)
    return eligible, lines


def verdict(claimed: D, eligible: D) -> str:
    if eligible == 0:
        return "not_covered"
    return "covered" if eligible == claimed else "partially_covered"
