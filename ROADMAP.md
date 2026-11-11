# ROADMAP

## 1. Generate the 360-doc corpus on the main PC + KoSIT-gate it (NEXT)
- Install Java ≥ 11, download validator v1.6.3 jar (Maven Central) and the
  XRechnung configuration release 2026-08-31 (see docs/MAIN-PC.md)
- Run `xbench generate` with rendering (reportlab + Pillow): PDFs, T0–T3
  degraded images, and the KoSIT gate on every document
- Acceptance: 360/360 documents pass KoSIT before entering the dataset; any
  failure is investigated (builder/template bug) before publishing
- Sanity-check the validator's real `<doc>-report.xml` against our parser
  (attribute names documented in NOTES.md, adjust if they differ)

## 2. Wire real model runners (main PC, GPU)
- Stand up vLLM for PaddleOCR-VL-1.6, GLM-OCR, olmOCR-2-7B, Qwen3-VL-8B;
  llama-cpp-python for german-ocr-3; transformers+docling for granite-docling
- Implement each adapter's `run()` against the local server/transformers API,
  keep the JSON-only contract
- API reference: glm-5.3-flash via the Z.ai Coding Plan endpoint
  (https://api.z.ai/api/coding/paas/v4, key XBENCH_ZAI_KEY) — pipeline STOPS
  on billing/endpoint errors, no pay-per-call fallback

## 3. First full run + leaderboard publication
- `xbench run --model <id> --split test` per model; `xbench score`
- Record validator/config versions in every result JSON
- Fill the README leaderboard with per-tier rollups; tag v0.1

## 4. Determinism & contamination checks
- 3-seed × 4-tier degradation ablations (plan §7 budget)
- Contamination note for Qwen-family models vs sinabis-style training data
- Pin exact versions in a lockfile; CI gate: config/spec mismatch must fail loudly

## 5. Later (v1+)
- Peppol BIS profile via itplr-kosit/validator-configuration-bis
- Real-scan tier (pending license: Aoschu, BKS-Lab)
- Held-out train/test split of layout families
- Credit-note/381 coverage beyond the 3 flagged layouts
