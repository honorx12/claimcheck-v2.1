from decimal import Decimal as D
import pytest
from pydantic import ValidationError
from app.rules import Rule, calc, validate_citations, verdict


def test_cap_copay_exclusion():
    items = [{"item": "Room charges", "quantity": 2, "amount": 12000},
             {"item": "Cosmetic kit", "quantity": 1, "amount": 500}]
    rules = [Rule(kind="room_rent_cap_per_day", value=D(5000), page=1, quote="x"),
             Rule(kind="exclusion", applies_to="cosmetic", page=1, quote="x"),
             Rule(kind="copay_pct", value=D(10), page=1, quote="x")]
    assert calc(items, rules)[0] == D("9000.00")          # (5000*2) minus 10%


def test_proportionate():
    items = [{"item": "Room charges", "quantity": 2, "amount": 16000},
             {"item": "Consultation fee", "quantity": 1, "amount": 4000},
             {"item": "Pharmacy", "quantity": 1, "amount": 3000},
             {"item": "Cosmetic kit", "quantity": 1, "amount": 500}]
    rules = [Rule(kind="room_rent_cap_per_day", value=D(5000), page=1, quote="x"),
             Rule(kind="room_rent_proportionate", page=1, quote="x"),
             Rule(kind="exclusion", applies_to="cosmetic", page=1, quote="x"),
             Rule(kind="copay_pct", value=D(10), page=1, quote="x")]
    assert calc(items, rules)[0] == D("13950.00")


def test_no_rules_means_unadjusted():
    assert calc([{"item": "Consultation", "quantity": 1, "amount": 4000}], [])[0] == D("4000.00")


def test_no_float_drift():
    items = [{"item": "A", "quantity": 1, "amount": "0.10"}, {"item": "B", "quantity": 1, "amount": "0.20"}]
    assert calc(items, [])[0] == D("0.30")


def test_fake_quote_rejected():
    ev = [{"page": 3, "content": "3.1 Room rent is capped at 1% of sum insured."}]
    bad = Rule(kind="copay_pct", value=D(20), page=3, quote="Co-pay of 20% applies")
    wrong_page = Rule(kind="room_rent_cap_per_day", value=D(1), page=4, quote="Room rent is capped")
    good = Rule(kind="room_rent_cap_per_day", value=D(1), page=3, quote="room  rent is\ncapped")
    assert validate_citations([bad, wrong_page, good], ev) == [good]


def test_empty_quote_rejected():
    assert validate_citations([Rule(kind="copay_pct", value=D(5), page=1, quote="  ")],
                              [{"page": 1, "content": "anything"}]) == []


@pytest.mark.parametrize("kw", [
    dict(kind="copay_pct"), dict(kind="copay_pct", value=D(101)),
    dict(kind="room_rent_cap_per_day", value=D(0)), dict(kind="exclusion"),
    dict(kind="exclusion", applies_to="  ")])
def test_incomplete_rule_rejected(kw):
    with pytest.raises(ValidationError):
        Rule(page=1, quote="q", **kw)


def test_verdict():
    assert verdict(D(100), D(100)) == "covered"
    assert verdict(D(100), D(0)) == "not_covered"
    assert verdict(D(100), D(50)) == "partially_covered"
