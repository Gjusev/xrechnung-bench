"""End-to-end offline smoke: fake adapter -> xml_builder -> scoring.
No GPU, no PDF rendering, no KoSIT jar required."""
import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.base import MissingCredentials, NeedsGPUDeps, resolve_field
from models.fake import FakeAdapter
from models import xml_builder, validator
from scoring import fields, arithmetic
from cli import _strip_uncertainty


class TestFakePipeline(unittest.TestCase):
    def test_fake_adapter_returns_canned_json(self):
        adapter = FakeAdapter()
        out = adapter.run(None, {"doc_id": "L00-T0-V0"})
        self.assertEqual(out["bt-1"], "RE-2026-0417")
        self.assertEqual(out["_model_id"], "fake")

    def test_full_offline_pipeline(self):
        adapter = FakeAdapter()
        predicted = adapter.run(None, None)
        with open(Path(__file__).resolve().parent.parent / "fixtures" / "ground_truth"
                  / "invoice-001.json", encoding="utf-8") as fh:
            truth = json.load(fh)
        scored = fields.compare_instances(predicted, truth)
        self.assertEqual(scored["metrics"]["counts"]["wrong"], 0)
        arith = arithmetic.check_consistency(predicted)
        self.assertTrue(arith["consistent"])
        # builder produces parseable XML from the model JSON
        xml = xml_builder.build_invoice_xml_document(_strip_uncertainty(predicted))
        import xml.etree.ElementTree as ET
        ET.fromstring(xml)

    def test_registry_stubs_require_gpu(self):
        from models.registry import get_adapter, ADAPTER_REGISTRY
        stub_ids = [m for m, c in ADAPTER_REGISTRY.items() if m != "fake"]
        for model_id in stub_ids:
            adapter = get_adapter(model_id)
            try:
                adapter.run(None, None)
            except NeedsGPUDeps as exc:
                self.assertIn("docs/MAIN-PC.md", str(exc))
            except MissingCredentials:
                pass  # API adapter without key — also a clean stop
            else:
                self.fail("adapter %s should not silently succeed offline" % model_id)

    def test_api_adapter_requires_key_and_stops_on_error(self):
        from models.registry import get_adapter
        import os
        old = os.environ.pop("XBENCH_ZAI_KEY", None)
        try:
            adapter = get_adapter("glm-5.3-flash-zai-api")
            with self.assertRaises(MissingCredentials):
                adapter.run("fixtures/invoices/invoice-001.xml", None)
            self.assertEqual(adapter.model_name, "glm-5.3-flash")
            self.assertEqual(adapter.base_url, "https://api.z.ai/api/coding/paas/v4")
        finally:
            if old:
                os.environ["XBENCH_ZAI_KEY"] = old

    def test_resolve_field_abstention_conventions(self):
        self.assertEqual(resolve_field(None), (None, False))
        self.assertEqual(resolve_field("not_found"), (None, False))
        self.assertEqual(resolve_field(""), (None, False))
        self.assertEqual(resolve_field({"value": "x", "uncertain": True}), ("x", True))
        self.assertEqual(resolve_field({"value": None, "uncertain": True}), (None, True))
        self.assertEqual(resolve_field("x"), ("x", False))


class TestCorpusSpec(unittest.TestCase):
    def test_spec_is_360_and_deterministic(self):
        from generator.generate import build_corpus_spec, build_layouts, TOTAL_DOCS
        a, b = build_corpus_spec(), build_corpus_spec()
        self.assertEqual(len(a), TOTAL_DOCS, "must be exactly 360")
        self.assertEqual(a, b, "spec must be deterministic")
        tiers = {d["tier"] for d in a}
        self.assertEqual(tiers, {"T0", "T1", "T2", "T3"})
        self.assertEqual(len({d["layout_id"] for d in a}), 30)
        self.assertEqual(len({d["seed"] for d in a}), TOTAL_DOCS, "seeds must be unique")

    def test_layouts_cover_30_families(self):
        from generator.generate import build_layouts
        layouts = build_layouts()
        self.assertEqual(len(layouts), 30)
        self.assertTrue({l["credit_note"] for l in layouts} == {True, False})
        self.assertEqual(len({l["name"] for l in layouts}), 30)

    def test_generate_offline_produces_corpus_and_kosit_gate(self):
        """Offline: XML + ground truth written, KoSIT skipped with explicit status."""
        from generator.generate import generate
        import os
        old_jar = os.environ.pop("XBENCH_VALIDATOR_JAR", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                manifest = generate(out_dir=tmp, validate=True, render=False, progress=False)
                self.assertEqual(manifest["total"], 360)
                self.assertFalse(manifest["validator"]["available"])
                self.assertEqual(manifest["validator"]["excluded_on_fail"], 0)
                for doc in manifest["documents"][:5]:
                    self.assertEqual(doc["kosit"]["status"], "skipped")
                    self.assertTrue((Path(tmp) / doc["xml"]).is_file())
                    self.assertTrue((Path(tmp) / doc["ground_truth"]).is_file())
                    self.assertIsNone(doc["pdf"])
                # manifest written and loadable
                loaded = json.loads((Path(tmp) / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(loaded["schema"], "xbench.corpus.v1")
        finally:
            if old_jar:
                os.environ["XBENCH_VALIDATOR_JAR"] = old_jar


class TestDegrade(unittest.TestCase):
    def test_png_roundtrip_and_transforms_pure_python(self):
        from generator import degrade
        import random
        w, h = 24, 16
        img = degrade.Img(w, h, bytes(bytearray(
            (x * 7 + y * 11) % 256 for y in range(h) for x in range(w) for _ in range(3))))
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.png"
            degrade.png_write(p, img)
            back = degrade.png_read(p)
            self.assertEqual((back.w, back.h), (w, h))
            self.assertEqual(back.pixels, img.pixels)
        rotated = degrade.rotate(img, 1.5)
        self.assertGreaterEqual(rotated.w, img.w)
        smaller = degrade.downscale(img, 2.0)
        self.assertEqual((smaller.w, smaller.h), (12, 8))
        noisy = degrade.add_noise(img, random.Random(42), sigma=10)
        self.assertEqual(len(noisy.pixels), len(img.pixels))
        stamped = degrade.stamp_overlay(img, random.Random(1), (2, 2, 10, 6))
        self.assertNotEqual(stamped.pixels, img.pixels)
        for tier in ("T0", "T1", "T2", "T3"):
            out, steps = degrade.apply_tier(img, tier, seed=1)
            self.assertTrue(steps)
        with self.assertRaises(ValueError):
            degrade.apply_tier(img, "T9", seed=1)


if __name__ == "__main__":
    unittest.main()
