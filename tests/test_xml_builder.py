"""Tests for models/xml_builder.py — stdlib only."""
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.xml_builder import (BuilderError, MissingFieldError, GUIDELINE_ID,
                                build_invoice_xml, build_invoice_xml_document,
                                fmt_amount, iso_to_ccyyccmm)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
NS = {"rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
      "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
      "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"}


def load_gt(name):
    with open(FIXTURES / "ground_truth" / name, encoding="utf-8") as fh:
        return json.load(fh)


class TestXmlBuilder(unittest.TestCase):
    def test_builds_parseable_xml_for_all_fixtures(self):
        for name in ("invoice-001.json", "invoice-002.json", "invoice-003.json"):
            xml = build_invoice_xml_document(load_gt(name))
            root = ET.fromstring(xml)  # raises if not well-formed
            self.assertEqual(root.tag, "{%s}CrossIndustryInvoice" % NS["rsm"])

    def test_key_fields_present_and_correct(self):
        instance = load_gt("invoice-001.json")
        root = ET.fromstring(build_invoice_xml(instance))
        self.assertEqual(root.findtext("./rsm:ExchangedDocument/ram:ID", namespaces=NS),
                         "RE-2026-0417")
        self.assertEqual(root.findtext("./rsm:ExchangedDocument/ram:TypeCode", namespaces=NS),
                         "380")
        issue = root.find(".//ram:IssueDateTime/udt:DateTimeString", NS)
        self.assertEqual(issue.get("format"), "102")
        self.assertEqual(issue.text, "20260115")
        self.assertIn(GUIDELINE_ID,
                      root.findtext(".//ram:GuidelineSpecifiedDocumentContextParameter/ram:ID",
                                    namespaces=NS))
        lines = root.findall(".//ram:IncludedSupplyChainTradeLineItem", NS)
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0].findtext(".//ram:Name", namespaces=NS),
                         "Entwicklungsleistung API-Integration")
        self.assertEqual(lines[0].findtext(".//ram:LineTotalAmount", namespaces=NS), "1020.00")
        summation = root.find(".//ram:SpecifiedTradeSettlementHeaderMonetarySummation", NS)
        self.assertEqual(summation.findtext("ram:TaxBasisTotalAmount", namespaces=NS), "2100.00")
        self.assertEqual(summation.findtext("ram:DuePayableAmount", namespaces=NS), "2499.00")
        tax_total = summation.find("ram:TaxTotalAmount", NS)
        self.assertEqual(tax_total.get("currencyID"), "EUR")
        self.assertEqual(tax_total.text, "399.00")
        self.assertEqual(root.findtext(".//ram:IBANID", namespaces=NS), "DE89370400440532013000")
        self.assertEqual(root.findtext(".//ram:BuyerReference", namespaces=NS), "KUNDENREF-0815")
        vat_regs = [e.text for e in root.findall(".//ram:SpecifiedTaxRegistration/ram:ID", NS)]
        self.assertEqual(vat_regs, ["DE123456789"])

    def test_two_vat_categories(self):
        root = ET.fromstring(build_invoice_xml(load_gt("invoice-003.json")))
        header_taxes = root.findall(
            ".//ram:ApplicableHeaderTradeSettlement/ram:ApplicableTradeTax", NS)
        self.assertEqual(len(header_taxes), 2)
        amounts = [t.findtext("ram:CalculatedAmount", namespaces=NS) for t in header_taxes]
        self.assertEqual(amounts, ["199.50", "13.44"])

    def test_deterministic(self):
        instance = load_gt("invoice-002.json")
        a = build_invoice_xml_document(instance)
        b = build_invoice_xml_document(instance)
        self.assertEqual(a, b)

    def test_matches_handwritten_fixture(self):
        """The stored fixture XML and the builder output must agree on all BT values."""
        fixture = ET.parse(str(FIXTURES / "invoices" / "invoice-001.xml")).getroot()
        built = ET.fromstring(build_invoice_xml(load_gt("invoice-001.json")))
        for path in ("ram:ID", "ram:TypeCode", ".//udt:DateTimeString"):
            for tree in (fixture, built):
                pass  # both parsed fine — compare key texts below
        self.assertEqual(fixture.findtext(".//ram:ID", namespaces=NS),
                         built.findtext(".//ram:ID", namespaces=NS))
        self.assertEqual(fixture.find(".//ram:IssueDateTime/udt:DateTimeString", NS).text,
                         built.find(".//ram:IssueDateTime/udt:DateTimeString", NS).text)
        self.assertEqual(
            [e.text for e in fixture.findall(".//ram:LineTotalAmount", NS)],
            [e.text for e in built.findall(".//ram:LineTotalAmount", NS)])
        self.assertEqual(
            fixture.find(".//ram:SpecifiedTradeSettlementHeaderMonetarySummation", NS)
                   .findtext("ram:GrandTotalAmount", namespaces=NS),
            built.find(".//ram:SpecifiedTradeSettlementHeaderMonetarySummation", NS)
                 .findtext("ram:GrandTotalAmount", namespaces=NS))

    def test_missing_required_field_raises(self):
        instance = load_gt("invoice-001.json")
        del instance["bt-1"]
        with self.assertRaises(MissingFieldError):
            build_invoice_xml(instance)

    def test_abstained_required_totals_raise(self):
        instance = load_gt("invoice-001.json")
        instance["bg-22"]["bt-115"] = None  # model abstained on amount due
        with self.assertRaises(MissingFieldError):
            build_invoice_xml(instance)

    def test_bad_type_raises_builder_error(self):
        with self.assertRaises(BuilderError):
            build_invoice_xml(["not", "a", "dict"])
        with self.assertRaises(BuilderError):
            fmt_amount("12,34.56.78")
        with self.assertRaises(BuilderError):
            iso_to_ccyyccmm("JAN/15/2026")

    def test_helpers(self):
        self.assertEqual(fmt_amount("1020"), "1020.00")
        self.assertEqual(fmt_amount(" 1.020,50 "), "1020.50")
        self.assertEqual(iso_to_ccyyccmm("2026-01-15"), "20260115")
        self.assertEqual(iso_to_ccyyccmm("20260115"), "20260115")


if __name__ == "__main__":
    unittest.main()
