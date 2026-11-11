"""Corpus generator: 360 documents = 30 layout families x 4 tiers x 3 variants.

`xbench generate` builds the corpus spec with deterministic seeds, derives
business data, writes ground-truth JSON + XRechnung XML via the deterministic
builder, gates every document through the KoSIT validator when available
(a document that FAILS KoSIT never enters the dataset) and renders/degrades
PDFs + images when the optional dependencies are installed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from models import validator, xml_builder
from . import business_data

REPO_ROOT = Path(__file__).resolve().parent.parent

N_LAYOUTS = 30
N_TIERS = 4
N_VARIANTS = 3
TOTAL_DOCS = N_LAYOUTS * N_TIERS * N_VARIANTS  # 360

SECTORS = ["it-services", "books-print", "consulting", "craft", "it-services",
           "books-print", "consulting", "craft"]
HEADER_STYLES = ["classic", "modern", "tabular"]
FONT_NAMES = ["Helvetica", "Times-Roman", "Courier"]

CREDIT_NOTE_LAYOUTS = {7, 17, 27}


def build_layouts(n: int = N_LAYOUTS) -> list[dict]:
    """Deterministic layout-family specs (visually distinct invoice shells)."""
    layouts = []
    for i in range(n):
        layouts.append({
            "id": i,
            "name": "L%02d-%s-%s" % (i, SECTORS[i % len(SECTORS)], HEADER_STYLES[i % len(HEADER_STYLES)]),
            "sector": SECTORS[i % len(SECTORS)],
            "header_style": HEADER_STYLES[i % len(HEADER_STYLES)],
            "number_format": "de" if i % 3 else "en",
            "date_format": ["de", "iso", "us-like"][i % 3],
            "font_name": FONT_NAMES[i % len(FONT_NAMES)],
            "font_size": [10, 11, 12][i % 3],
            "line_height": [14, 15, 16][i % 3],
            "header_rule": i % 2 == 0,
            "table_rules": i % 4 != 1,
            "uppercase": i % 5 == 2,
            "credit_note": i in CREDIT_NOTE_LAYOUTS,
        })
    return layouts


def doc_seed(layout_id: int, tier: str, variant: int) -> int:
    digest = hashlib.sha256(("xbench-v1|%d|%s|%d" % (layout_id, tier, variant)).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def build_corpus_spec() -> list[dict]:
    """The 360-document corpus spec — identical on every machine, forever."""
    layouts = build_layouts()
    spec = []
    for layout in layouts:
        for tier in ("T0", "T1", "T2", "T3"):
            for variant in range(N_VARIANTS):
                seed = doc_seed(layout["id"], tier, variant)
                case = business_data.make_business_case(seed, variant, layout)
                spec.append({
                    "doc_id": "L%02d-%s-V%d" % (layout["id"], tier, variant),
                    "layout_id": layout["id"],
                    "layout_name": layout["name"],
                    "tier": tier,
                    "variant": variant,
                    "seed": seed,
                    "axes": case["meta"],
                })
    assert len(spec) == TOTAL_DOCS
    return spec


def generate(out_dir: str | Path = None, validate: bool = True, render: bool = True,
             progress: bool = True) -> dict:
    """Build the corpus. Returns the manifest dict (also written to manifest.json).

    Gate: when the KoSIT validator is available every generated XML must PASS
    before it enters the dataset; failures are kept on disk but marked
    `excluded: true` in the manifest and counted.
    """
    out = Path(out_dir) if out_dir else (REPO_ROOT / "corpus")
    (out / "xml").mkdir(parents=True, exist_ok=True)
    (out / "ground_truth").mkdir(parents=True, exist_ok=True)
    if render:
        (out / "pdf").mkdir(exist_ok=True)
        (out / "images").mkdir(exist_ok=True)

    val_ok, val_reason = validator.validator_available() if validate else (False, "validation_disabled")
    render_ok = True
    degrade_ok = True
    if render:
        from . import render as render_mod
        try:
            import reportlab  # noqa: F401
        except ImportError:
            render_ok = False
        try:
            import PIL  # noqa: F401
        except ImportError:
            degrade_ok = False

    layouts = {l["id"]: l for l in build_layouts()}
    entries = []
    n_excluded = 0
    for spec in build_corpus_spec():
        seed = spec["seed"]
        layout = layouts[spec["layout_id"]]
        case = business_data.make_business_case(seed, spec["variant"], layout)
        instance = case["instance"]
        xml_text = xml_builder.build_invoice_xml_document(instance)
        xml_path = out / "xml" / (spec["doc_id"] + ".xml")
        xml_path.write_text(xml_text, encoding="utf-8")
        gt_path = out / "ground_truth" / (spec["doc_id"] + ".json")
        gt_path.write_text(json.dumps(instance, ensure_ascii=False, indent=1), encoding="utf-8")

        kosit = {"status": "skipped", "reason": val_reason, "errors": [], "warnings": []}
        if val_ok:
            res = validator.run_validator(xml_path, workdir=str(out))
            kosit = {"status": res["status"], "reason": res["reason"],
                     "errors": [e.get("id") for e in res.get("errors", [])],
                     "warnings": [w.get("id") for w in res.get("warnings", [])]}
        excluded = kosit["status"] == "fail"
        n_excluded += excluded

        pdf_status = None
        image_status = None
        if render:
            pdf_path = out / "pdf" / (spec["doc_id"] + ".pdf")
            img_path = out / "images" / (spec["doc_id"] + ".png")
            try:
                if render_ok:
                    render_mod.render_pdf(instance, layout, pdf_path)
                    pdf_status = "rendered"
                else:
                    pdf_status = "skipped_no_reportlab"
            except Exception as exc:  # noqa: BLE001 — render errors recorded, never fatal
                pdf_status = "error: %s" % exc
            try:
                if degrade_ok and render_ok:
                    from . import degrade
                    render_mod.render_png(instance, layout, img_path, dpi=300)
                    raw = degrade.png_read(img_path)
                    degraded, steps = degrade.apply_tier(raw, spec["tier"], seed)
                    degrade.png_write(str(img_path), degraded)
                    image_status = "degraded:" + ",".join(steps)
                else:
                    image_status = "skipped_no_pillow_or_reportlab"
            except Exception as exc:  # noqa: BLE001
                image_status = "error: %s" % exc

        entry = dict(spec)
        entry.update({
            "ground_truth": str(gt_path.relative_to(out)),
            "xml": str(xml_path.relative_to(out)),
            "pdf": str(pdf_path.relative_to(out)) if pdf_status == "rendered" else None,
            "image": str(img_path.relative_to(out)) if image_status and str(image_status).startswith("degraded") else None,
            "kosit": kosit,
            "excluded": excluded,
        })
        if pdf_status:
            entry["pdf_status"] = pdf_status
        if image_status:
            entry["image_status"] = image_status
        entries.append(entry)
        if progress and len(entries) % 60 == 0:
            print("  %d/%d documents built" % (len(entries), TOTAL_DOCS))

    manifest = {
        "schema": "xbench.corpus.v1",
        "total": TOTAL_DOCS,
        "n_layouts": N_LAYOUTS,
        "n_tiers": N_TIERS,
        "n_variants": N_VARIANTS,
        "validator": {"available": val_ok, "reason": val_reason,
                      "jar": str(validator.DEFAULT_JAR),
                      "config_release": validator.CONFIG_RELEASE_URL,
                      "excluded_on_fail": n_excluded},
        "documents": entries,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    if progress:
        print("corpus: %d docs, %d excluded by KoSIT, validator=%s (%s)"
              % (len(entries), n_excluded, "available" if val_ok else "skipped", val_reason))
    return manifest
