"""Run-level scoring and leaderboard rendering.

Input: results/<model>.jsonl (one JSON per line, written by `xbench run`) and
the corpus ground truth. Output: aggregate metrics + a markdown leaderboard
row; `xbench score` prints the full table.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import fields, arithmetic

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_results(path: Path) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_ground_truth(corpus_dir: Path) -> dict[str, dict]:
    gt = {}
    for p in sorted((corpus_dir / "ground_truth").glob("*.json")):
        with open(p, encoding="utf-8") as fh:
            gt[p.stem] = json.load(fh)
    return gt


def score_run(results_path: Path, corpus_dir: Path) -> dict:
    results = load_results(results_path)
    truth = load_ground_truth(Path(corpus_dir))
    per_tier: dict[str, list[dict]] = {}
    overall = {"docs": 0, "kosit_pass": 0, "kosit_fail": 0, "kosit_skipped": 0,
               "arithmetic_consistent": 0, "field_correct": 0, "field_wrong": 0,
               "field_abstained": 0, "field_hallucinated": 0, "field_total": 0}
    doc_scores = []
    for res in results:
        doc_id = res["doc_id"]
        t = truth.get(doc_id)
        if t is None:
            continue
        cmp = fields.compare_instances(res.get("predicted", {}), t)
        arith = arithmetic.check_consistency(res.get("predicted", {}))
        kv = res.get("kosit") or {}
        status = kv.get("status", "skipped")
        tier = res.get("tier", "?")
        entry = {
            "doc_id": doc_id, "tier": tier,
            "metrics": cmp["metrics"], "summary": cmp["summary"],
            "arithmetic_consistent": arith["consistent"],
            "kosit_status": status,
            "kosit_error_ids": kv.get("errors", []),
        }
        per_tier.setdefault(tier, []).append(entry)
        doc_scores.append(entry)
        overall["docs"] += 1
        overall["kosit_pass"] += status == "pass"
        overall["kosit_fail"] += status == "fail"
        overall["kosit_skipped"] += status not in ("pass", "fail")
        overall["arithmetic_consistent"] += arith["consistent"]
        for s in ("correct", "wrong", "abstained", "hallucinated"):
            overall["field_" + s if s != "hallucinated" else "field_hallucinated"] += cmp["summary"][s]
    overall["field_total"] = sum(
        overall["field_correct"] + overall["field_wrong"] + overall["field_abstained"]
        + overall["field_hallucinated"] for _ in [0]
    )

    def agg(entries: list[dict]) -> dict:
        n = len(entries) or 1
        answered = correct = abstained = halluc = 0
        kosit_decided = 0
        for e in entries:
            c = e["metrics"]["counts"]
            answered += c["correct"] + c["wrong"]
            correct += c["correct"]
            abstained += c["abstained"]
            halluc += c["hallucinated"]
            kosit_decided += e["kosit_status"] in ("pass", "fail")
        total = answered + abstained
        return {
            "docs": len(entries),
            "field_accuracy": (correct / total) if total else None,
            "accuracy_on_answered": (correct / answered) if answered else None,
            "coverage": (answered / total) if total else None,
            "hallucination_rate": (halluc / total) if total else None,
            # n/a when the validator never ran — a skip must not read as 0%
            "kosit_pass_rate": (sum(e["kosit_status"] == "pass" for e in entries) / kosit_decided)
                               if kosit_decided else None,
            "kosit_skipped": sum(e["kosit_status"] not in ("pass", "fail") for e in entries),
            "arithmetic_consistency": (sum(e["arithmetic_consistent"] for e in entries) / n),
        }

    out = {
        "model": results[0].get("model", results_path.stem) if results else results_path.stem,
        "results_path": str(results_path),
        "docs_scored": overall["docs"],
        "overall": agg(doc_scores),
        "per_tier": {tier: agg(entries) for tier, entries in sorted(per_tier.items())},
        "documents": doc_scores,
    }
    return out


def leaderboard_row(score: dict) -> str:
    o = score["overall"]
    def pct(v):
        return ("%.1f%%" % (100 * v)) if v is not None else "n/a"
    return "| %s | %d | %s | %s | %s | %s | %s | %s |" % (
        score["model"], score["docs_scored"],
        pct(o["field_accuracy"]), pct(o["accuracy_on_answered"]), pct(o["coverage"]),
        pct(o["hallucination_rate"]), pct(o["kosit_pass_rate"]), pct(o["arithmetic_consistency"]),
    )


LEADERBOARD_HEADER = (
    "| Model | Docs | Field accuracy | Acc. on answered | Coverage | Halluc. rate | KoSIT pass | Arithmetic |"
    "\n|---|---|---|---|---|---|---|---|"
)


def render_leaderboard_table(scores: list[dict]) -> str:
    return "\n".join([LEADERBOARD_HEADER] + [leaderboard_row(s) for s in scores])
