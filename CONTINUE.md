# CONTINUE.md

How to pick this project back up without re-reading everything.

## Where things stand (2026-11-12)
- Offline-complete: generator, xml_builder, validator integration (subprocess
  + tolerant report/SVRL parser), scoring, CLI. `python3 -m unittest discover
  -s tests` is green (37 tests, stdlib only).
- The 360-doc corpus generates offline (XML + ground truth + manifest,
  KoSIT steps recorded as `skipped (java_not_found)`). Not committed.
- No model has run. No leaderboard numbers exist. That is the next milestone.

## Next actions (in order)
1. Main PC setup → docs/MAIN-PC.md (Java, KoSIT jar + config into `tools/`,
   Python venv with reportlab + Pillow, GPU stack per model).
2. `xbench generate` on the main PC → verify 360/360 pass the KoSIT gate;
   diff one real `<doc>-report.xml` against our parser assumptions (NOTES.md).
3. Wire the real adapters in models/registry.py (currently stubs that raise
   NeedsGPUDeps with a pointer to docs/MAIN-PC.md).
4. Run all models, `xbench score`, fill the README leaderboard.

## Rules that must survive refactors
- Models return **JSON only** (schema.json). `models/xml_builder.py` is the
  single XML writer. Never let an adapter emit XML.
- A missing validator/dep is a **skipped status**, never a pass, never fake data.
- Offline tests stay stdlib-only and green (`python3 -m unittest`).
- API reference runs **only** via the Z.ai Coding Plan endpoint, model pinned
  to **glm-5.3-flash**; on billing/endpoint errors the pipeline stops.
- Conventional commits, English. Repo: github.com/Gjusev/xrechnung-bench.
