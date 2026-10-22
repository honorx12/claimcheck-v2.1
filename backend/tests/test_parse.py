import pathlib
from decimal import Decimal as D
import pytest
from app import parse
from app.parse import Bill, Item, split_clauses, structure_bill
from app.redact import redact

FIX = pathlib.Path(__file__).parent / "fixtures"


def test_clause_styles():
    text = "1. Definitions\n3.1 Room rent is capped.\n3.2. Second.\n4) Co-pay applies.\n30 days wait."
    got = list(split_clauses(text))
    assert [c for c, _ in got] == ["1", "3.1", "3.2", "4"]
    assert "30 days wait." in got[-1][1]


def test_preamble_has_no_clause_id():
    got = list(split_clauses("Policy wording\n1. Definitions"))
    assert got[0][0] is None and got[1][0] == "1"


def test_sniff_uses_bytes():
    assert parse.sniff(b"%PDF-1.4 x") == "pdf"
    assert parse.sniff(b"\x89PNG\r\n\x1a\nxx") == "png"
    assert parse.sniff(b"\xff\xd8\xffxx") == "jpg"
    assert parse.sniff(b"GIF89a") is None and parse.sniff(b"MZ\x90") is None


@pytest.mark.skipif(not (FIX / "02_partial_policy.pdf").exists(), reason="run python -m scripts.make_fixtures")
def test_policy_pdf_to_rows():
    pages = parse.extract_pages((FIX / "02_partial_policy.pdf").read_bytes(), "pdf")
    assert len(pages) == 1 and pages[0][2] == 1.0
    ids = [r["clause_id"] for r in parse.policy_rows(pages)]
    assert {"3.1", "4.1", "5.1"} <= set(ids)


def test_page_cap(monkeypatch):
    if not (FIX / "02_partial_policy.pdf").exists():
        pytest.skip("fixtures")
    with pytest.raises(parse.ParseError):
        parse.extract_pages((FIX / "02_partial_policy.pdf").read_bytes(), "pdf", max_pages=0)


def test_unreadable_image():
    with pytest.raises(parse.ParseError):
        parse.extract_pages(b"\x89PNG\r\n\x1a\nbroken", "png")


PAGE = "Room charges 2 days Rs 12,000.00\nConsultation fee Rs 4,000.00\nTotal Rs 16,000.00"


def fake(items, total=None):
    return lambda sys, usr, model: Bill(items=items, total=total)


def test_hallucinated_line_dropped():
    jc = fake([Item(item="Room", amount=D(12000), source_text="Room charges 2 days Rs 12,000.00"),
               Item(item="Ghost MRI", amount=D(9000), source_text="MRI scan Rs 9,000.00")], D(16000))
    items, flags, _ = structure_bill([(1, PAGE, 0.95)], jc)
    assert [i["item"] for i in items] == ["Room"] and "line_dropped_unverified" in flags


def test_amount_must_appear_in_source():
    jc = fake([Item(item="Consult", amount=D(4500), source_text="Consultation fee Rs 4,000.00")])
    items, flags, _ = structure_bill([(1, PAGE, 0.95)], jc)
    assert items == [] and "no_items" in flags


def test_total_mismatch_flagged_not_corrected():
    jc = fake([Item(item="Room", amount=D(12000), source_text="Room charges 2 days Rs 12,000.00")], D(16000))
    items, flags, total = structure_bill([(1, PAGE, 0.95)], jc)
    assert "total_mismatch" in flags and items[0]["amount"] == D(12000) and total == D(16000)


def test_low_conf_flag_and_clean_case():
    both = [Item(item="Room", amount=D(12000), source_text="Room charges 2 days Rs 12,000.00"),
            Item(item="Consult", amount=D(4000), source_text="Consultation fee Rs 4,000.00")]
    assert structure_bill([(1, PAGE, 0.95)], fake(both, D(16000)))[1] == []
    assert "low_ocr_conf" in structure_bill([(1, PAGE, 0.5)], fake(both, D(16000)))[1]


def test_pii_redacted_before_llm():
    seen = {}

    def jc(sys, usr, model):
        seen["usr"] = usr
        return Bill(items=[])
    structure_bill([(1, "Patient a@b.com 9876543210 123456789012\nRoom Rs 100.00", 1.0)], jc)
    assert "a@b.com" not in seen["usr"] and "9876543210" not in seen["usr"] and "123456789012" not in seen["usr"]
    assert "Rs 100.00" in seen["usr"]


def test_redact_keeps_amounts():
    assert redact("Total 1234567.00 mail x@y.in") == "Total 1234567.00 mail [EMAIL]"
