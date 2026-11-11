# MAIN-PC runbook — GPU runs for xrechnung-bench

Everything below happens on the GPU box (24 GB VRAM class, e.g. RTX 4090/A100
mined from the 4A research budget: **≈30–50 GPU-h total**, ~€40–100 spot for a
week). The offline dev box runs none of this.

## 0. Base setup

```bash
sudo apt-get install -y openjdk-21-jre-headless   # Java >= 11 required
git clone https://github.com/Gjusev/xrechnung-bench && cd xrechnung-bench
python3 -m venv .venv && source .venv/bin/activate
pip install reportlab pillow                      # rendering + degradations
python3 -m unittest discover -s tests             # must stay green
```

## 1. KoSIT validator (pinned versions — do NOT track `latest`)

```bash
mkdir -p tools && cd tools
curl -L -o validator-1.6.3-standalone.jar \
  https://repo1.maven.org/maven2/org/kosit/validator/1.6.3/validator-1.6.3-standalone.jar
curl -L -o xr-config.zip \
  https://github.com/itplr-kosit/validator-configuration-xrechnung/releases/download/v2026-08-31/xrechnung-3.0.2-validator-configuration-2026-08-31.zip
unzip xr-config.zip && rm xr-config.zip   # leaves scenarios.xml + rules/
cd ..

export XBENCH_VALIDATOR_JAR=$PWD/tools/validator-1.6.3-standalone.jar
export XBENCH_SCENARIOS_XML=$PWD/tools/scenarios.xml

# smoke: the three fixtures must validate (see NOTES.md caveat 2)
python3 cli.py validate --xml fixtures/invoices/invoice-001.xml
python3 cli.py validate --xml fixtures/invoices/invoice-002.xml
python3 cli.py validate --xml fixtures/invoices/invoice-003.xml
```

Check the generated `fixtures/invoices/invoice-001-report.xml` against
`fixtures/kosit_report_valid.xml` — if attribute names differ, fix
`models/validator.py` and regenerate the fixture (NOTES.md caveat 1).

## 2. Corpus generation (CPU-mostly, ~10 h wall / ~2 GPU-h)

```bash
xbench generate          # 360 docs: PDF + T0-T3 images + KoSIT gate on each
```

Acceptance: manifest shows `validator.available: true`, `excluded_on_fail: 0`.
Any KoSIT failure = builder/template bug — fix before running models.

## 3. Local model stacks

| Adapter | HF repo | License | Stack | Est. VRAM |
|---|---|---|---|---|
| paddleocr-vl-1.6 | PaddlePaddle/PaddleOCR-VL-1.6 | Apache-2.0 | paddleocr or vLLM | 4–6 GB |
| glm-ocr-local | zai-org/GLM-OCR | MIT (pipeline Apache-2.0) | vLLM/SGLang/Ollama | 4–6 GB |
| olmocr-2-7b | allenai/olmOCR-2-7B-1025 | Apache-2.0 | vLLM (FP8 variant ~10 GB) | 16–20 GB BF16 |
| german-ocr-3 | Keyven/german-ocr-3 | Apache-2.0 | llama-cpp-python (GGUF 2.7 GB) | 4–6 GB |
| granite-docling-258m | ibm-granite/granite-docling-258M | Apache-2.0 | transformers + docling | 2–3 GB |
| qwen3-vl-8b | Qwen/Qwen3-VL-8B-Instruct | Apache-2.0 | vLLM | 18–22 GB BF16 / 8–12 GB quant |

```bash
pip install vllm torch transformers docling llama-cpp-python paddleocr paddlepaddle
# example: vLLM server for Qwen3-VL
vllm serve Qwen/Qwen3-VL-8B-Instruct --max-model-len 8192
# HF license note: all six local models are Apache-2.0/MIT per their model
# cards (verified 2026-11-12) — no gating beyond HF terms.
```

Then implement each adapter's `run()` in `models/registry.py` against the
local endpoint (JSON-only contract; see ROADMAP item 2) and run:

```bash
xbench run --model qwen3-vl-8b --split test     # ~4–8 GPU-h for all 7 models total
xbench score
```

## 4. API reference — Z.ai Coding Plan (owner decision)

- Endpoint: `https://api.z.ai/api/coding/paas/v4` (OpenAI-compatible), model
  **pinned to `glm-5.3-flash`** — no other model id is offered or defaulted.
- Key: `export XBENCH_ZAI_KEY=<coding-plan key>`
- The adapter (`glm-5.3-flash-zai-api` in models/registry.py) STOPS the
  pipeline on billing/quota/endpoint errors. **Never fall back to
  pay-per-call providers.** Results are reported separately from local models
  (it isolates the "API vs local" delta).
- Runs through the Coding Plan; no other provider is configured anywhere in
  this repo.

## 5. Expected wall time (budget from plan §7)

| Step | Estimate |
|---|---|
| Corpus generation + KoSIT gate | ~10 h wall (≈2 GPU-h) |
| Main runs: 360 docs × 7 local models + 1 API ref | ~4–8 GPU-h |
| Seed/degradation ablations (3 seeds × 4 tiers) | ~8–15 GPU-h |
| Validator reconstruction + SVRL parsing (CPU) | ~2 h |
| Debug/baselines | ~10–20 GPU-h |
| **Total** | **≈30–50 GPU-h** |

## 6. Publishing results

- `xbench score` writes `results/leaderboard.json`; paste the table into
  README (per-tier rollups included in the JSON).
- Record pinned versions (validator jar, config release, model revisions) in
  the run notes — CI must fail loudly on version mismatch.
