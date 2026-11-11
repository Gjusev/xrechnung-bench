"""Scoring math tests on fixtures: normalization, per-field exact match,
abstention/coverage, arithmetic consistency."""
import copy
import json
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoring import fields, arithmetic, normalize, leaderboard

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def load_gt(name="invoice-001.json"):
    with open(FIXTURES / "ground_truth" / name, encoding="utf-8") as fh:
        return json.load(fh)


def load_fake():
    with open(FIXTURES / "fake_model_output.json", encoding="utf-8") as fh:
        return json.load(fh)["predicted"]


class TestNormalization(unittest.TestCase):
    def test_amounts(self):
        self.assertTrue(normalize.amounts_equal("1.234,56", "1234.56"))
        self.assertTrue(normalize.amounts_equal("2499.00", "2499.01"))
        self.assertFalse(normalize.amounts_equal("2499.00", "2499.02"))
        self.assertEqual(normalize.to_decimal("€ 1.234,56"), normalize.to_decimal("1234.56"))

    def test_dates(self):
        self.assertEqual(normalize.normalize_date("15.01.2026"), "2026-01-15")
        self.assertEqual(normalize.normalize_date("2026-01-15"), "2026-01-15")
        self.assertIsNone(normalize.normalize_date("Morgen"))

    def test_iban_vat(self):
        self.assertEqual(normalize.normalize_iban("de89 3704 0044 0532 0130 00"),
                         "DE89370400440532013000")
        self.assertEqual(normalize.normalize_vat_id(" de123456789 "), "DE123456789")


class TestFieldScoring(unittest.TestCase):
    def test_perfect_extraction_scores_full(self):
        pred, truth = load_fake(), load_gt()
        result = fields.compare_instances(pred, truth)
        # bt-2 uses DE date format, bt-9 an uncertainty wrapper, bt-84 a spaced
        # IBAN, bt-48 abstains on an absent truth field — all handled.
        m = result["metrics"]
        self.assertEqual(m["counts"]["wrong"], 0)
        self.assertEqual(m["counts"]["hallucinated"], 0)
        # accuracy on answered fields is perfect; raw field_accuracy honestly
        # counts the bt-9 uncertainty abstention as non-correct
        self.assertEqual(m["accuracy_on_answered"], 1.0)
        self.assertAlmostEqual(m["field_accuracy"], 47 / 48)
        self.assertGreaterEqual(m["counts"]["abstained"], 1)
        self.assertLess(m["coverage"], 1.0)

    def test_wrong_amount_detected(self):
        pred, truth = load_fake(), load_gt()
        pred["bg-22"]["bt-115"] = "2498.00"
        result = fields.compare_instances(pred, truth)
        self.assertEqual(result["metrics"]["counts"]["wrong"], 1)
        self.assertEqual(result["metrics"]["accuracy_on_answered"],
                         result["metrics"]["counts"]["correct"]
                         / (result["metrics"]["counts"]["correct"] + 1))

    def test_off_by_one_cent_still_correct(self):
        pred, truth = load_fake(), load_gt()
        pred["bg-22"]["bt-115"] = "2499.01"
        self.assertEqual(fields.compare_instances(pred, truth)["metrics"]["counts"]["wrong"], 0)

    def test_hallucinated_buyer_vat(self):
        pred, truth = load_fake(), load_gt()
        pred["bt-48"] = "DE000000000"  # truth bt-48 is null
        result = fields.compare_instances(pred, truth)
        self.assertEqual(result["metrics"]["counts"]["hallucinated"], 1)
        self.assertGreater(result["metrics"]["hallucination_rate"], 0)

    def test_hand_computed_abstention_case(self):
        """Mini case with exact expected numbers: 4 fields, 1 abstained."""
        truth = {"bt-1": "A-1", "bt-2": "2026-01-01", "bt-5": "EUR", "bt-9": "2026-01-15"}
        pred = {"bt-1": "A-1", "bt-2": "01.01.2026", "bt-5": None, "bt-9": "2026-02-15"}
        res = fields.compare_instances(pred, truth)
        # bt-1 correct, bt-2 correct (date normalization), bt-5 abstained,
        # bt-9 wrong -> answered=3, correct=2, coverage=0.75, acc_on_answered=2/3
        m = res["metrics"]
        self.assertEqual(m["counts"], {"correct": 2, "wrong": 1, "abstained": 1,
                                       "hallucinated": 0, "not_present": 0})
        self.assertAlmostEqual(m["coverage"], 0.75)
        self.assertAlmostEqual(m["accuracy_on_answered"], 2 / 3)
        self.assertAlmostEqual(m["field_accuracy"], 0.5)


class TestArithmetic(unittest.TestCase):
    def test_ground_truth_fixtures_are_consistent(self):
        for name in ("invoice-001.json", "invoice-002.json", "invoice-003.json"):
            res = arithmetic.check_consistency(load_gt(name))
            self.assertTrue(res["consistent"], "%s: %s" % (name, res["checks"]))

    def test_broken_totals_detected(self):
        truth = load_gt()
        truth["bg-22"]["bt-115"] = "9999.99"
        res = arithmetic.check_consistency(truth)
        self.assertFalse(res["consistent"])
        names = [c["name"] for c in res["checks"] if not c["ok"]]
        self.assertTrue(any("bt-115" in n for n in names))

    def test_vat_math_detected(self):
        truth = load_gt()
        truth["bg-23"][0]["bt-117"] = "400.00"  # 19% of 2100 is 399
        res = arithmetic.check_consistency(truth)
        self.assertFalse(res["consistent"])
        self.assertEqual(res["max_abs_error"], "1.00")

    def test_generated_business_cases_consistent(self):
        from generator import business_data
        from generator.generate import build_layouts, doc_seed
        for layout in build_layouts()[:6]:
            for variant in range(3):
                case = business_data.make_business_case(
                    doc_seed(layout["id"], "T1", variant), variant, layout)
                res = arithmetic.check_consistency(case["instance"])
                self.assertTrue(res["consistent"],
                                "layout %d variant %d: %s" % (layout["id"], variant, res["checks"]))


class TestLeaderboard(unittest.TestCase):
    def test_leaderboard_row_renders(self):
        pred, truth = load_fake(), load_gt()
        score = {
            "model": "fake", "docs_scored": 1,
            "overall": {
                "field_accuracy": 1.0, "accuracy_on_answered": 1.0,
                "coverage": fields.compare_instances(pred, truth)["metrics"]["coverage"],
                "hallucination_rate": 0.0, "kosit_pass_rate": 0.0,
                "arithmetic_consistency": 1.0,
            },
        }
        row = leaderboard.leaderboard_row(score)
        self.assertIn("fake", row)
        self.assertIn("100.0%", row)
        self.assertIn("0.0%", row)


if __name__ == "__main__":
    unittest.main()
