#!/usr/bin/env python3
"""xbench — CLI for the XRechnung benchmark.

Subcommands:
  generate  build the 360-doc corpus (spec + XML + ground truth; PDF/images
            and the KoSIT gate when the optional deps are installed)
  run       run one model adapter over the corpus -> results/<model>.jsonl
  score     aggregate results -> leaderboard table
  models    list registered adapters
  validate  run/skip the KoSIT validator on a single XML file
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from models import validator  # noqa: E402
from models.base import MissingCredentials, NeedsGPUDeps  # noqa: E402
from models.fake import FakeAdapter  # noqa: E402
from models.registry import ADAPTER_REGISTRY, get_adapter  # noqa: E402
from scoring import leaderboard  # noqa: E402

RESULTS_DIR = REPO_ROOT / "results"
DEFAULT_CORPUS = REPO_ROOT / "corpus"


def _strip_uncertainty(instance: dict) -> dict:
    """Flatten {'value', 'uncertain'} wrappers for the XML builder; abstentions
    (None/'not_found') stay None and trigger MissingFieldError — which is the
    honest measurement, not a bug."""
    import copy

    from models.base import resolve_field

    out = copy.deepcopy(instance)
    for key, val in out.items():
        if isinstance(val, dict) and "value" in val:
            out[key], _ = resolve_field(val)
    return out


def cmd_generate(args) -> int:
    from generator.generate import generate
    manifest = generate(out_dir=args.out, validate=not args.no_validate, render=not args.no_render)
    excluded = manifest["validator"]["excluded_on_fail"]
    print("manifest: %s" % (Path(args.out) if args.out else DEFAULT_CORPUS / "manifest.json"))
    if manifest["validator"]["available"] and excluded:
        print("WARNING: %d documents failed KoSIT and were excluded — investigate before publishing." % excluded)
    return 0


def cmd_run(args) -> int:
    corpus = Path(args.corpus) if args.corpus else DEFAULT_CORPUS
    manifest_path = corpus / "manifest.json"
    if not manifest_path.is_file():
        print("ERROR: %s not found — run `xbench generate` first." % manifest_path, file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    try:
        adapter = get_adapter(args.model)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    docs = [d for d in manifest["documents"]
            if not d.get("excluded") and (args.split in ("all", "test") or d["tier"].lower() == args.split)]
    if args.limit:
        docs = docs[: args.limit]

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / ("%s.jsonl" % adapter.model_id)
    skipped: list[str] = []
    with open(out_path, "w", encoding="utf-8") as out:
        for doc in docs:
            input_path = doc.get("image") or doc.get("pdf")
            input_path = str(corpus / input_path) if input_path else None
            if adapter.model_id != "fake" and not input_path:
                skipped.append("%s: no rendered image/pdf (offline corpus?)" % doc["doc_id"])
                continue
            started = time.time()
            try:
                predicted = adapter.run(input_path, doc)
            except (NeedsGPUDeps, MissingCredentials) as exc:
                print("STOP: adapter %s cannot run here — no fallback, no partial results "
                      "published.\n%s" % (adapter.model_id, exc), file=sys.stderr)
                if not out.tell():
                    out_path.unlink(missing_ok=True)
                return 3
            record = {
                "doc_id": doc["doc_id"],
                "tier": doc["tier"],
                "model": adapter.model_id,
                "predicted": predicted,
                "duration_s": round(time.time() - started, 3),
            }
            if input_path:
                # Signature metric path: rebuild XRechnung XML from the model's
                # JSON via the deterministic builder, then KoSIT-validate THAT.
                from models import xml_builder
                try:
                    rebuilt_xml = xml_builder.build_invoice_xml_document(
                        _strip_uncertainty(predicted))
                    rebuilt_path = corpus / "rebuilt" / (doc["doc_id"] + ".xml")
                    rebuilt_path.parent.mkdir(parents=True, exist_ok=True)
                    rebuilt_path.write_text(rebuilt_xml, encoding="utf-8")
                    kosit_in = validator.run_validator(rebuilt_path)
                    record["kosit"] = {
                        "status": kosit_in["status"],
                        "reason": kosit_in.get("reason"),
                        "errors": [e.get("id") for e in kosit_in.get("errors", [])],
                    }
                except xml_builder.BuilderError as exc:
                    record["kosit"] = {"status": "fail", "reason": "rebuild_failed: %s" % exc,
                                       "errors": []}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    if skipped:
        print("%d docs skipped (no rendered input): first: %s" % (len(skipped), skipped[0]))
    print("wrote %d results -> %s" % (len(docs), out_path))
    return 0


def cmd_score(args) -> int:
    corpus = Path(args.corpus) if args.corpus else DEFAULT_CORPUS
    paths = sorted(RESULTS_DIR.glob(args.models_glob)) if args.models_glob else []
    if args.model:
        paths = [RESULTS_DIR / ("%s.jsonl" % args.model)]
    if not paths:
        print("No results found in %s — run `xbench run --model ...` first." % RESULTS_DIR)
        return 0
    scores = []
    for path in paths:
        scores.append(leaderboard.score_run(path, corpus))
    print(leaderboard.render_leaderboard_table(scores))
    out_path = RESULTS_DIR / "leaderboard.json"
    out_path.write_text(json.dumps(scores, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nwrote %s" % out_path)
    return 0


def cmd_models(_) -> int:
    from models.registry import _LocalStubAdapter, ApiZAIAdapter
    print("registered adapters:")
    for model_id, cls in ADAPTER_REGISTRY.items():
        if model_id == "fake":
            note = "offline canned fixture"
        elif issubclass(cls, ApiZAIAdapter):
            note = "API reference via Z.ai Coding Plan (XBENCH_ZAI_KEY), model %s" % cls.model_name
        elif issubclass(cls, _LocalStubAdapter):
            note = "local GPU adapter — %s (%s)" % (cls.hf_repo, cls.license)
        else:
            note = ""
        print("  %-24s %s" % (model_id, note))
    return 0


def cmd_validate(args) -> int:
    ok, reason = validator.validator_available()
    if not ok:
        print("KoSIT validator SKIPPED (%s). Setup: docs/MAIN-PC.md" % reason)
        return 0
    res = validator.run_validator(args.xml)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res["status"] in ("pass", "skipped") else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="xbench", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="build the 360-doc corpus")
    g.add_argument("--out", default=None, help="output dir (default ./corpus)")
    g.add_argument("--no-validate", action="store_true", help="skip the KoSIT gate")
    g.add_argument("--no-render", action="store_true", help="skip PDF/image rendering")
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("run", help="run a model adapter over the corpus")
    r.add_argument("--model", required=True, help="adapter id (see `xbench models`)")
    r.add_argument("--split", default="test", choices=["t0", "t1", "t2", "t3", "test", "all"],
                   help="corpus split; default 'test' = all tiers (v0.1 ships no held-out "
                        "split yet — tiers are the difficulty axis)")
    r.add_argument("--corpus", default=None)
    r.add_argument("--limit", type=int, default=None)
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("score", help="aggregate results into a leaderboard")
    s.add_argument("--model", default=None)
    s.add_argument("--models-glob", default="*.jsonl")
    s.add_argument("--corpus", default=None)
    s.set_defaults(func=cmd_score)

    sub.add_parser("models", help="list model adapters").set_defaults(func=cmd_models)

    v = sub.add_parser("validate", help="KoSIT-validate a single XML file (or skip)")
    v.add_argument("--xml", required=True)
    v.set_defaults(func=cmd_validate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
