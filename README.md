# xrechnung-bench

An open benchmark measuring whether **local vision models** can convert German
invoices (PDF/scans) into **valid XRechnung 3.0.2** — checked with the official
**KoSIT validator**, scored per EN 16931 business term (BT), with arithmetic
consistency and an abstention/coverage protocol.

**Author:** Youssef Ouhaghi · License: MIT · Status: v0.1 — offline-tested, no results yet

---

## Why

Existing document-AI benchmarks measure markdown fidelity or generic field QA.
None of them closes the loop to **legal usability**: a German e-invoice is only
usable if the official KoSIT validator accepts the reconstructed XML. This
benchmark ties vision quality to that check:

1. **BT-keyed field accuracy** — exact match per EN 16931 field (amounts with
   ±0.01 Decimal tolerance, ISO dates, IBAN, VAT ids), 360 synthetic documents
   with exact ground truth derived from the source XML.
2. **KoSIT pass rate (signature metric)** — model output is structured JSON;
   a deterministic builder turns it into XRechnung CII XML; the official
   validator (v1.6.3 + configuration release 2026-08-31) accepts or rejects it.
3. **Arithmetic consistency** — line sums, VAT math, totals chain (BR-CO-10…16
   equivalents), computed from the model's own numbers, no ground truth needed.
4. **Abstention protocol** — models may answer `null` / `"not_found"` /
   `{"value": x, "uncertain": true}`; we report **accuracy-on-answered vs
   coverage** and hallucination rate, never raw accuracy alone.

## Honest status

| Component | State |
|---|---|
| Corpus generator (360 docs, deterministic seeds) | ✅ implemented, offline-tested (XML + ground truth) |
| KoSIT gate in the generate pipeline | ✅ implemented — **skipped on this box (no Java), runs on the main PC** |
| PDF rendering + scan degradations (T0–T3) | ✅ implemented — reportlab/Pillow optional, skipped offline, pure-python PNG fallback |
| Model adapters (6 local + 1 API reference) | ✅ interface + stubs with explicit GPU-dep errors; **no inference run yet** |
| Scoring (fields, arithmetic, abstention, leaderboard) | ✅ implemented and unit-tested |
| **Actual model runs / leaderboard numbers** | ❌ **not yet — runs happen on GPU, see docs/MAIN-PC.md** |

## Leaderboard

*No results yet — runs happen on GPU (docs/MAIN-PC.md). The table below is a
template; nothing has been measured.*

| Model | Docs | Field accuracy | Acc. on answered | Coverage | Halluc. rate | KoSIT pass | Arithmetic |
|---|---|---|---|---|---|---|---|
| _(empty — no results yet)_ | | | | | | | |

Planned candidates (licenses verified on HF model cards, 2026-11-12):
PaddleOCR-VL-1.6 (Apache-2.0) · GLM-OCR local (MIT) · olmOCR-2-7B (Apache-2.0) ·
german-ocr-3 (Apache-2.0) · granite-docling-258M (Apache-2.0) ·
Qwen3-VL-8B-Instruct (Apache-2.0) · API reference: **glm-5.3-flash via Z.ai
Coding Plan** (proprietary, reported separately from local models).

## Architecture

```
document (PDF/scan image)
        │  model adapters (models/) — JSON only, NEVER XML
        ▼
structured JSON — schema.json, EN 16931 subset, BT-keyed
        │  models/xml_builder.py — the ONLY place XML is written
        ▼
XRechnung 3.0.2 CII XML (deterministic, byte-stable)
        │  models/validator.py — KoSIT jar via subprocess (optional, explicit skip)
        ▼
acceptance verdict + SVRL findings (BR-DE-* rule ids)
        │  scoring/ — fields.py, arithmetic.py, leaderboard.py
        ▼
results/<model>.jsonl → xbench score → leaderboard
```

Hard rule: **model output never writes XML.** Adapters return JSON
conforming to `schema.json`; `models/xml_builder.py` owns all XML
construction; every document is validated by the KoSIT jar when available.

## Quickstart (offline, no GPU — what runs on any machine)

```bash
git clone https://github.com/Gjusev/xrechnung-bench && cd xrechnung-bench
python3 -m unittest discover -s tests      # offline test suite, stdlib only
./xbench models                            # list adapters
./xbench generate                          # 360-doc corpus: XML + ground truth + manifest
./xbench run --model fake                  # canned-JSON adapter, offline smoke
./xbench score                             # leaderboard (real models need GPU)
```

Offline behavior is explicit, never faked: `generate` records
`kosit: skipped (java_not_found)` per document; PDF/image steps record
`skipped_no_reportlab` / `skipped_no_pillow`; real adapters raise a clear
"requires GPU + deps" error instead of pretending.

## Corpus

360 documents = **30 layout families × 4 difficulty tiers × 3 business
variants**, all from deterministic seeds (`doc_seed` = SHA-256 of layout/tier/variant):

- **T0** digital-native render · **T1** office scan (±0.5°, mild noise) ·
  **T2** bad scan (96–150 DPI, ±3°, low contrast) · **T3** worst case (T2 +
  stamps over totals/date regions)
- Variants: B2B 19 % VAT · B2G with Leitweg-ID and 7 % VAT · mixed 19 %+7 %
  (three layouts produce 381 credit notes)
- Ground truth = the source instance (same data that generated the XML);
  every document passes through the KoSIT gate before entering the dataset
  (enforced when the validator is installed — failures are excluded)
- All companies, IBANs (mod-97 checksum-valid) and VAT ids are synthetic;
  the corpus is CC-BY-4.0 once published

The corpus itself is **not committed** — it is byte-reproducible via
`xbench generate` (manifest records every seed).

## CLI

```
xbench generate [--out DIR] [--no-validate] [--no-render]
xbench run --model <id> --split test|t0..t3|all [--corpus DIR] [--limit N]
xbench score [--model <id>] [--models-glob '*.jsonl']
xbench models          # adapter registry
xbench validate --xml FILE
```

Environment: `XBENCH_VALIDATOR_JAR`, `XBENCH_SCENARIOS_XML` (KoSIT paths),
`XBENCH_ZAI_KEY` (API reference only). `results/` holds per-model JSONL;
`xbench score` writes `results/leaderboard.json` and prints the table.

## License & attribution

MIT — see LICENSE. The KoSIT validator (Apache-2.0, © KoSIT) and the
XRechnung validator configuration are external pinned dependencies, not
redistributed here; download commands in docs/MAIN-PC.md.
