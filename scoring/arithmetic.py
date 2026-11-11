"""Arithmetic consistency of a model prediction — runs WITHOUT ground truth.

Checks (BR-CO-10/13/14/15/16/17 equivalents, +-0.01 tolerance):
  * sum of line nets (BT-131) = BT-106
  * BT-109 = BT-106 - allowances + charges (allowances/charges v0.1: zero)
  * per VAT category: BT-117 = BT-116 x BT-119 / 100
  * BT-110 = sum of BT-117
  * BT-112 = BT-109 + BT-110
  * BT-115 = BT-112 - BT-113
Also usable on real scans, since it needs only the model's own numbers.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .normalize import to_decimal

TOLERANCE = Decimal("0.01")


def _dec(value) -> Decimal | None:
    if value in (None, "", "not_found"):
        return None
    d = to_decimal(value)
    if d is None:
        raise ValueError("not a decimal: %r" % (value,))
    return d


def _check(checks: list, name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def check_consistency(instance: dict) -> dict:
    """Return {"consistent": bool, "checks": [...], "max_abs_error": Decimal}."""
    checks: list[dict] = []
    max_err = Decimal("0")

    def note(name: str, a: Decimal | None, b: Decimal | None, detail: str = ""):
        nonlocal max_err
        if a is None or b is None:
            _check(checks, name, False, "missing operand " + detail)
            return None
        err = abs(a - b)
        max_err = max(max_err, err)
        _check(checks, name, err <= TOLERANCE,
               "%s != %s (%s)" % (a, b, detail) if err > TOLERANCE else detail or "ok")
        return err

    def safe(_fn, *args):
        try:
            return _fn(*args)
        except ValueError:
            _check(checks, _fn.__name__, False, "unparseable amount")
            return None

    lines = instance.get("bg-25") or []
    totals = instance.get("bg-22") or {}

    # 1. line sums
    line_nets = []
    for i, ln in enumerate(lines):
        try:
            line_nets.append(_dec(ln.get("bt-131")))
        except ValueError:
            _check(checks, "line_parse", False, "line %d bt-131 unparseable" % (i + 1))
            line_nets.append(None)
    if line_nets and all(v is not None for v in line_nets):
        note("bt-106 = sum(lines bt-131)",
             _dec(totals.get("bt-106")), sum(line_nets, Decimal("0")), "BR-CO-10")
    elif totals.get("bt-106") is not None:
        _check(checks, "bt-106 = sum(lines bt-131)", False, "some line nets unparseable")

    # 2. totals chain
    bt106 = safe(_dec, totals.get("bt-106"))
    bt109 = safe(_dec, totals.get("bt-109"))
    note("bt-109 = bt-106 - allowances + charges", bt109, bt106, "BR-CO-13")

    # 3. VAT breakdown math
    breakdown = instance.get("bg-23") or []
    vat_sum = Decimal("0")
    all_ok = bool(breakdown)
    for i, cat in enumerate(breakdown):
        try:
            base, rate, vat = (_dec(cat.get("bt-116")), _dec(cat.get("bt-119")), _dec(cat.get("bt-117")))
        except ValueError:
            _check(checks, "vat_category_parse", False, "category %d unparseable" % (i + 1))
            all_ok = False
            continue
        if None in (base, rate, vat):
            _check(checks, "vat_category_%d" % (i + 1), False, "missing operand")
            all_ok = False
            continue
        expected = (base * rate / Decimal("100")).quantize(Decimal("0.01"))
        ok = abs(expected - vat) <= TOLERANCE
        max_err = max(max_err, abs(expected - vat))
        _check(checks, "bt-117 = bt-116 x bt-119/100 (cat %d)" % (i + 1), ok,
               "expected %s got %s" % (expected, vat))
        vat_sum += vat
    bt110 = safe(_dec, totals.get("bt-110"))
    if bt110 is not None:
        note("bt-110 = sum(bt-117)", bt110, vat_sum, "BR-CO-14")
        if bt109 is not None:
            bt112 = safe(_dec, totals.get("bt-112"))
            note("bt-112 = bt-109 + bt-110", bt112, bt109 + bt110, "BR-CO-15")
            bt113 = safe(_dec, totals.get("bt-113")) or Decimal("0")
            note("bt-115 = bt-112 - bt-113", safe(_dec, totals.get("bt-115")),
                 bt112 - bt113 if bt112 is not None else None, "BR-CO-16")

    consistent = bool(checks) and all(c["ok"] for c in checks)
    return {"consistent": consistent, "checks": checks, "max_abs_error": str(max_err)}
