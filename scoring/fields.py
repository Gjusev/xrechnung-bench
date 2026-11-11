"""Per-field exact match per BT field + abstention (coverage) metrics.

Scored field set and types mirror schema.json. Amounts, dates, IBAN, VAT ids
get type-aware normalization before exact match.
"""
from __future__ import annotations

from collections import defaultdict

from . import normalize
from .normalize import amounts_equal

# (field_key, kind) — kinds: amount, date, text, code, iban, vat_id, number
SCORED_SCALAR_FIELDS = [
    ("bt-1", "text"),
    ("bt-2", "date"),
    ("bt-3", "code"),
    ("bt-5", "code"),
    ("bt-9", "date"),
    ("bt-10", "text"),
    ("bt-20", "text"),
    ("bt-27", "text"),
    ("bt-31", "vat_id"),
    ("bt-44", "text"),
    ("bt-48", "vat_id"),
    ("bt-82", "code"),
    ("bt-84", "iban"),
    ("bt-86", "code"),
]

SCALAR_KINDS = dict(SCORED_SCALAR_FIELDS)

ADDRESS_FIELDS = {
    "bg-5": [("bt-35", "text"), ("bt-37", "text"), ("bt-38", "text"), ("bt-40", "code")],
    "bg-8": [("bt-50", "text"), ("bt-52", "text"), ("bt-53", "text"), ("bt-55", "code")],
}

TOTALS_FIELDS = [
    ("bt-106", "amount"),
    ("bt-109", "amount"),
    ("bt-110", "amount"),
    ("bt-112", "amount"),
    ("bt-113", "amount"),
    ("bt-115", "amount"),
]

LINE_FIELDS = [
    ("bt-153", "text"),
    ("bt-129", "number"),
    ("bt-130", "code"),
    ("bt-146", "amount"),
    ("bt-131", "amount"),
    ("bt-151", "code"),
    ("bt-152", "number"),
]

BREAKDOWN_FIELDS = [
    ("bt-116", "amount"),
    ("bt-117", "amount"),
    ("bt-119", "number"),
    ("bt-120", "code"),
]

ABSTAIN_MARKERS = {None, "", "not_found"}


def resolve_field(value):
    """(concrete_value_or_None, uncertain) — see models/base.resolve_field."""
    if isinstance(value, dict) and "value" in value:
        inner = value["value"]
        if inner in ABSTAIN_MARKERS:
            return None, bool(value.get("uncertain"))
        return inner, bool(value.get("uncertain"))
    if value is None or isinstance(value, (dict, list)) or value in ABSTAIN_MARKERS:
        return None, False
    return value, False


def _values_equal(kind, pred, truth) -> bool:
    if kind == "amount":
        return amounts_equal(pred, truth)
    if kind == "date":
        return normalize.normalize_date(pred) == normalize.normalize_date(truth)
    if kind == "iban":
        return normalize.normalize_iban(pred) == normalize.normalize_iban(truth)
    if kind == "vat_id":
        return normalize.normalize_vat_id(pred) == normalize.normalize_vat_id(truth)
    if kind == "number":
        return normalize.normalize_number(pred) == normalize.normalize_number(truth)
    if kind in ("code",):
        return normalize.normalize_code(pred) == normalize.normalize_code(truth)
    return normalize.normalize_text(pred) == normalize.normalize_text(truth)


def compare_scalar(pred_val, truth_val, kind):
    """Return one of: correct, wrong, abstained, hallucinated, not_present.

    not_present: field absent in ground truth AND the model abstained —
    neither accuracy nor hallucination credit.
    An uncertainty wrapper ({"value": x, "uncertain": true}) counts as an
    abstention even when a value is present — the model declined to commit.
    """
    pred, uncertain = resolve_field(pred_val)
    truth, _ = resolve_field(truth_val)
    if truth is None:
        return "hallucinated" if pred is not None else "not_present"
    if pred is None or uncertain:
        return "abstained"
    return "correct" if _values_equal(kind, pred, truth) else "wrong"


def _iter_scalar_pairs(pred_instance: dict, truth_instance: dict):
    """Yield (bucket, field_key, kind, pred_value, truth_value) for all scored scalars."""
    for key, kind in SCORED_SCALAR_FIELDS:
        if key in truth_instance or key in pred_instance:
            yield "document", key, kind, pred_instance.get(key), truth_instance.get(key)
    for group, fields in ADDRESS_FIELDS.items():
        pg = pred_instance.get(group) or {}
        tg = truth_instance.get(group) or {}
        for key, kind in fields:
            if key in tg or key in pg:
                yield group, key, kind, pg.get(key), tg.get(key)
    pt = pred_instance.get("bg-22") or {}
    tt = truth_instance.get("bg-22") or {}
    for key, kind in TOTALS_FIELDS:
        if key in tt or key in pt:
            yield "bg-22", key, kind, pt.get(key), tt.get(key)


def _match_lines(pred_lines, truth_lines):
    """Greedy match predicted lines to truth lines by name, then by index."""
    used = set()
    pairs = []
    for tl in truth_lines:
        tname = normalize.normalize_text(tl.get("bt-153"))
        match = None
        for i, pl in enumerate(pred_lines):
            if i in used:
                continue
            if normalize.normalize_text(pl.get("bt-153")) == tname:
                match = i
                break
        if match is None:
            for i, pl in enumerate(pred_lines):
                if i not in used:
                    match = i
                    break
        if match is not None:
            used.add(match)
            pairs.append((pred_lines[match], tl))
        else:
            pairs.append((None, tl))
    for i, pl in enumerate(pred_lines):
        if i not in used:
            pairs.append((pl, None))
    return pairs


def compare_instances(pred_instance: dict, truth_instance: dict) -> dict:
    """Full per-field comparison.

    Returns {"fields": {field_key: {bucket, status, truth, predicted, uncertain}},
             "summary": counts per status,
             "metrics": {field_accuracy, accuracy_on_answered, coverage,
                         hallucination_rate, per_field: {...}}}
    """
    fields: dict[str, dict] = {}
    counts = defaultdict(int)

    def record(field_key, bucket, status, truth=None, pred=None, uncertain=False):
        counts[status] += 1
        fields[field_key] = {"bucket": bucket, "status": status,
                             "truth": truth, "predicted": pred,
                             "uncertain": uncertain}

    # scalar document fields
    seen = set()
    for bucket, key, kind, pv, tv in _iter_scalar_pairs(pred_instance, truth_instance):
        status = compare_scalar(pv, tv, kind)
        pred_resolved, uncertain = resolve_field(pv)
        record(key, bucket, status, tv, pred_resolved, uncertain)
        seen.add(key)

    # line items (matched pairs)
    pred_lines = pred_instance.get("bg-25") or []
    truth_lines = truth_instance.get("bg-25") or []
    line_correct = line_total = 0
    for i, (pl, tl) in enumerate(_match_lines(pred_lines, truth_lines)):
        for key, kind in LINE_FIELDS:
            field_key = "bg-25[%d].%s" % (i + 1, key)
            pv = (pl or {}).get(key)
            tv = (tl or {}).get(key)
            if key not in (tl or {}) and key not in (pl or {}):
                continue
            status = compare_scalar(pv, tv, kind)
            record(field_key, "bg-25", status, tv, pv)
            if status in ("correct", "wrong"):
                line_total += 1
                line_correct += status == "correct"
    fields["_lines"] = {"bucket": "bg-25", "status": "group",
                        "line_accuracy": (line_correct / line_total) if line_total else None}

    # VAT breakdown: match by (category, rate); never mutate the caller's lists
    remaining = list(pred_instance.get("bg-23") or [])
    truth_bd = truth_instance.get("bg-23") or []
    for i, tb in enumerate(truth_bd):
        key_pair = (normalize.normalize_code(tb.get("bt-120")), normalize.normalize_number(tb.get("bt-119")))
        pb = None
        for cand in remaining:
            cpair = (normalize.normalize_code(cand.get("bt-120")), normalize.normalize_number(cand.get("bt-119")))
            if cpair == key_pair:
                pb = cand
                remaining.remove(cand)
                break
        for fkey, kind in BREAKDOWN_FIELDS:
            pv = (pb or {}).get(fkey)
            tv = tb.get(fkey)
            if tv is None and pv is None:
                continue
            status = compare_scalar(pv, tv, kind)
            record("bg-23[%d].%s" % (i + 1, fkey), "bg-23", status, tv, pv)
    for i, pb in enumerate(remaining):  # predicted categories missing from truth
        for fkey, kind in BREAKDOWN_FIELDS:
            pv = pb.get(fkey)
            if pv is None:
                continue
            status = compare_scalar(pv, None, kind)
            record("bg-23[extra].%s" % fkey, "bg-23", status, None, pv)

    summary = {s: counts.get(s, 0) for s in
               ("correct", "wrong", "abstained", "hallucinated", "not_present")}
    answered = summary["correct"] + summary["wrong"]
    total_truth = answered + summary["abstained"]
    metrics = {
        "field_accuracy": (summary["correct"] / total_truth) if total_truth else None,
        "accuracy_on_answered": (summary["correct"] / answered) if answered else None,
        "coverage": (answered / total_truth) if total_truth else None,
        "hallucination_rate": (summary["hallucinated"] / total_truth) if total_truth else None,
        "counts": summary,
    }
    return {"fields": fields, "summary": summary, "metrics": metrics}
