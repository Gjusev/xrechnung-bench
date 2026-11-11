# NOTES.md

Engineering notes, verified facts and open caveats.

## Verified facts (research 2026-11-11/12, plan 4A)
- KoSIT validator **v1.6.3** (Apache-2.0), Maven Central `org.kosit:validator`;
  standalone jar: `https://repo1.maven.org/maven2/org/kosit/validator/1.6.3/validator-1.6.3-standalone.jar`
- Validator configuration release **v2026-08-31** for XRechnung **3.0.2**
  (`xrechnung-3.0.2-validator-configuration-2026-08-31.zip`), Java ≥ 11
- Headless run: `java -jar validator.jar -s scenarios.xml -r <repo> -h invoice.xml`
- EN 16931 BT numbering **verified against the standard's rule texts**
  (Peppol PINT/UBL rule listings, 2026-11-12): BT-106 line-net sum, BT-109 net
  total, BT-110 total VAT, BT-112 gross, BT-113 paid, BT-115 due; lines
  BT-126/129/130/131/146/151/152/153; breakdown BT-116/117/119/120; parties
  BT-27/31/40/44/55; buyer reference BT-10 (Leitweg-ID, BR-DE-15); IBAN BT-84.
  The earlier plan table (§1.2) had BT-10/11/14 and BT-109/110 wrong — this
  repo uses the corrected mapping in schema.json.

## Caveats to re-verify on the main PC (no Java here)
1. **Report XML attribute names.** The KoSIT report parser
   (models/validator.py) is tolerant (namespace-agnostic, verdict|result,
   assertion|failed-assert) but was written from documented structure, not
   live output. First action on the main PC: run the validator on one fixture,
   diff `fixtures/kosit_report_valid.xml` against the real `<doc>-report.xml`,
   adjust parser/fixture if needed.
2. **Fixture XML validity.** The three fixture invoices are hand-written CII
   D16B following the XRechnung structure; they could NOT be run through the
   KoSIT validator on this box (no Java). Validate all three on the main PC
   before treating them as known-good.
3. **Leitweg-ID format.** Fixture 002 uses `05116-39370-49`; if the validator's
   BT-10 regex rejects it, adjust fixture + generator pattern.
4. **Credit notes (381)** appear in layouts 7/17/27 variant 2 with negative
   line nets (positive prices/quantities). Validator reaction not yet verified.
5. **PDF rendering (reportlab)** and image degradations (Pillow path incl.
   JPEG steps) are written but untested here — no reportlab/Pillow-free box.
   The pure-python PNG codec IS tested offline.

## Design decisions
- **JSON-only contract.** Model output never touches XML. Missing required BT
  fields raise MissingFieldError in the builder → recorded as
  `kosit: fail (rebuild_failed)`, an honest measurement.
- **Abstention semantics:** `null` / absent / `"not_found"` / `{"value", …,
  "uncertain": true}` all count as abstentions; `field_accuracy` includes
  abstentions in the denominator (the honest number), `accuracy_on_answered`
  excludes them; headline = accuracy-on-answered vs coverage.
- **Corpus decomposition:** 30 layouts × 4 tiers × 3 business variants = 360
  (equivalent coverage to the plan's 30 × 3 render styles × 4 tiers).
- **Seeds:** SHA-256("xbench-v1|layout|tier|variant")[:8] — unique, stable
  across machines and Python versions (not `hash()`, which is salted).
- **Corpus not committed:** byte-reproducible; the manifest records seeds.
- **Offline skips are explicit statuses** in the manifest/result records
  (`kosit_skipped`, `pdf_skipped_no_reportlab`, `jpeg_skipped_no_pil`).
- **KoSIT pass rate is n/a (not 0%)** when the validator never ran.
- API reference: Z.ai Coding Plan endpoint only, model pinned
  glm-5.3-flash; billing errors stop the pipeline (owner decision).
- results/*.jsonl and corpus/ are gitignored; fixtures and tests are the
  committed evidence of correctness.

## XRechnung CII builder details
- Guideline ID: `urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0`
- Element order follows CII D16B schema (ExchangedDocument: ID, TypeCode,
  IssueDateTime; MonetarySummation: LineTotal, ChargeTotal, AllowanceTotal,
  TaxBasis, TaxTotal(currencyID), GrandTotal, TotalPrepaid, DuePayable).
- Quantities serialized with 4 decimals, amounts with 2, format code 102 dates.
