"""Validator parser tests against KoSIT report fixtures + explicit-skip path."""
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import validator

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class TestReportParsing(unittest.TestCase):
    def test_valid_report(self):
        parsed = validator.parse_document_report(FIXTURES / "kosit_report_valid.xml")
        self.assertEqual(parsed["verdict"], "valid")
        self.assertEqual(parsed["error_ids"], [])
        self.assertEqual(parsed["warning_ids"], ["BR-DE-31"])

    def test_invalid_report(self):
        parsed = validator.parse_document_report(FIXTURES / "kosit_report_invalid.xml")
        self.assertEqual(parsed["verdict"], "invalid")
        self.assertEqual(parsed["error_ids"], ["BR-CO-15", "BR-DE-1"])

    def test_svrl_parsing(self):
        findings = validator.parse_svrl(FIXTURES / "kosit_report.svrl.xml")
        self.assertEqual([f["id"] for f in findings], ["BR-CO-15", "BR-DE-1"])
        self.assertTrue(all(f["text"] for f in findings))
        self.assertEqual(findings[0]["flag"], "fatal")


class TestRunValidator(unittest.TestCase):
    def test_missing_jar_is_skipped_never_faked(self):
        """Without jar/java the result is an explicit skip — never a pass."""
        res = validator.run_validator(FIXTURES / "invoices" / "invoice-001.xml")
        self.assertEqual(res["status"], "skipped")
        self.assertIsNone(res["verdict"])
        self.assertIn(res["reason"],
                      ("java_not_found", "validator_jar_missing (%s)" % validator.DEFAULT_JAR,
                       "scenarios_xml_missing (%s)" % validator.DEFAULT_SCENARIOS,
                       "validation_disabled", "no_report_written", "validator_timeout"))

    def test_command_shape(self):
        from pathlib import Path as P
        cmd = validator.build_command(P("invoice.xml"), "validator.jar",
                                      "scenarios.xml", P("/tmp/repo"))
        self.assertEqual(cmd[:4], ["java", "-jar", "validator.jar", "-s"])
        self.assertIn("-h", cmd)
        self.assertIn("invoice.xml", cmd)

    def test_availability_probe(self):
        ok, reason = validator.validator_available()
        self.assertIsInstance(ok, bool)
        self.assertTrue(reason)  # always explains itself


if __name__ == "__main__":
    unittest.main()
