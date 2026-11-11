"""Deterministic XRechnung 3.0.2 (CII D16B) builder.

This module OWNS all XML writing in the benchmark. Model output is structured
JSON (schema.json, EN 16931 subset) and never XML; this builder is the only
place that turns JSON into XRechnung XML. Output is byte-identical for
identical input (no timestamps, no randomness, stable element order).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from typing import Any

RSM = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
QDT = "urn:un:unece:uncefact:data:standard:QualifiedDataType:100"
RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
UDT = "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"
XSI = "http://www.w3.org/2001/XMLSchema-instance"

GUIDELINE_ID = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"

for prefix, uri in (("rsm", RSM), ("qdt", QDT), ("ram", RAM), ("udt", UDT), ("xsi", XSI)):
    ET.register_namespace(prefix, uri)


class BuilderError(ValueError):
    """Raised when the JSON instance cannot be turned into valid CII XML."""


class MissingFieldError(BuilderError):
    """Raised when a BT field required by the EN 16931 subset schema is absent."""


def _sub(parent: ET.Element, qname: str, text: str | None = None, **attrs: str) -> ET.Element:
    el = ET.SubElement(parent, qname)
    if text is not None:
        el.text = text
    for k, v in attrs.items():
        el.set(k, v)
    return el


def _q(ns: str, tag: str) -> str:
    return "{%s}%s" % (ns, tag)


def _parse_decimal(value) -> Decimal:
    """Liberal decimal parsing: plain and German (1.234,56) formats."""
    s = str(value).strip().replace(" ", "").replace("\u00a0", "")
    if "," in s:
        if s.rfind(",") > s.rfind("."):  # German decimal comma
            s = s.replace(".", "").replace(",", ".")
        else:  # EN thousands commas
            s = s.replace(",", "")
    try:
        return Decimal(s)
    except InvalidOperation as exc:
        raise BuilderError("not a decimal amount: %r" % (value,)) from exc


def fmt_amount(value: Any) -> str:
    """Format a money/quantity-like value as a plain two-decimal string."""
    try:
        return str(_parse_decimal(value).quantize(Decimal("0.01")))
    except BuilderError:
        raise
    except Exception as exc:
        raise BuilderError("not a decimal amount: %r" % (value,)) from exc


def fmt_quantity(value: Any) -> str:
    try:
        return str(_parse_decimal(value).quantize(Decimal("0.0001")))
    except BuilderError:
        raise
    except Exception as exc:
        raise BuilderError("not a decimal quantity: %r" % (value,)) from exc


def iso_to_ccyyccmm(date_iso: str) -> str:
    """2026-01-15 -> 20260115 (CII DateTimeString format code 102)."""
    s = str(date_iso).strip()
    if len(s) == 8 and s.isdigit():
        return s
    parts = s.replace(".", "-").split("-")
    if len(parts) != 3:
        raise BuilderError("unsupported date format, want ISO YYYY-MM-DD: %r" % date_iso)
    y, m, d = (p.zfill(2 if i else 4) for i, p in enumerate(parts))
    return y + m + d


def _require(obj: dict, key: str, where: str = "instance") -> Any:
    val = obj.get(key)
    if val is None or val == "" or val == "not_found":
        raise MissingFieldError("missing required field %s in %s" % (key, where))
    return val


def _address(parent: ET.Element, addr: dict | None, keys: dict[str, str], who: str) -> None:
    if addr is None:
        raise MissingFieldError("missing address %s" % who)
    postal = _sub(parent, _q(RAM, "PostalTradeAddress"))
    if addr.get(keys["postcode"]):
        _sub(postal, _q(RAM, "PostcodeCode"), str(addr[keys["postcode"]]))
    if addr.get(keys["line1"]):
        _sub(postal, _q(RAM, "LineOne"), str(addr[keys["line1"]]))
    _sub(postal, _q(RAM, "CityName"), str(_require(addr, keys["city"], who)))
    _sub(postal, _q(RAM, "CountryID"), str(_require(addr, keys["country"], who)))


def build_invoice_xml(instance: dict) -> str:
    """Build a complete CII CrossIndustryInvoice document from schema.json JSON.

    Raises MissingFieldError for required BT fields the model abstained on —
    that is a measurement result, not a formatting bug.
    """
    if not isinstance(instance, dict):
        raise BuilderError("instance must be a dict, got %s" % type(instance).__name__)

    root = ET.Element(_q(RSM, "CrossIndustryInvoice"))

    ctx = _sub(root, _q(RSM, "ExchangedDocumentContext"))
    guideline = _sub(ctx, _q(RAM, "GuidelineSpecifiedDocumentContextParameter"))
    _sub(guideline, _q(RAM, "ID"), GUIDELINE_ID)

    doc = _sub(root, _q(RSM, "ExchangedDocument"))
    _sub(doc, _q(RAM, "ID"), str(_require(instance, "bt-1", "document")))
    _sub(doc, _q(RAM, "TypeCode"), str(_require(instance, "bt-3", "document")))
    issue = _sub(doc, _q(RAM, "IssueDateTime"))
    _sub(issue, _q(UDT, "DateTimeString"), iso_to_ccyyccmm(_require(instance, "bt-2", "document")), format="102")

    txn = _sub(root, _q(RSM, "SupplyChainTradeTransaction"))

    # --- lines (BG-25) -------------------------------------------------
    lines = instance.get("bg-25") or []
    if not lines:
        raise MissingFieldError("missing required line items (bg-25)")
    for i, line in enumerate(lines, start=1):
        li = _sub(txn, _q(RAM, "IncludedSupplyChainTradeLineItem"))
        ldoc = _sub(li, _q(RAM, "AssociatedDocumentLineDocument"))
        _sub(ldoc, _q(RAM, "LineID"), str(line.get("bt-126") or i))
        product = _sub(li, _q(RAM, "SpecifiedTradeProduct"))
        _sub(product, _q(RAM, "Name"), str(_require(line, "bt-153", "line %d" % i)))
        agr = _sub(li, _q(RAM, "SpecifiedLineTradeAgreement"))
        price = _sub(agr, _q(RAM, "NetPriceProductTradePrice"))
        _sub(price, _q(RAM, "ChargeAmount"), fmt_amount(_require(line, "bt-146", "line %d" % i)))
        delivery = _sub(li, _q(RAM, "SpecifiedLineTradeDelivery"))
        _sub(delivery, _q(RAM, "BilledQuantity"), fmt_quantity(_require(line, "bt-129", "line %d" % i)),
             unitCode=str(line.get("bt-130") or "C62"))
        settle = _sub(li, _q(RAM, "SpecifiedLineTradeSettlement"))
        tax = _sub(settle, _q(RAM, "ApplicableTradeTax"))
        _sub(tax, _q(RAM, "TypeCode"), "VAT")
        _sub(tax, _q(RAM, "CategoryCode"), str(line.get("bt-151") or "S"))
        _sub(tax, _q(RAM, "RateApplicablePercent"), fmt_amount(line.get("bt-152") or "0.00"))
        summ = _sub(settle, _q(RAM, "SpecifiedTradeSettlementLineMonetarySummation"))
        _sub(summ, _q(RAM, "LineTotalAmount"), fmt_amount(_require(line, "bt-131", "line %d" % i)))

    # --- header agreement ----------------------------------------------
    agreement = _sub(txn, _q(RAM, "ApplicableHeaderTradeAgreement"))
    if instance.get("bt-10"):
        _sub(agreement, _q(RAM, "BuyerReference"), str(instance["bt-10"]))
    seller = _sub(agreement, _q(RAM, "SellerTradeParty"))
    _sub(seller, _q(RAM, "Name"), str(_require(instance, "bt-27", "seller")))
    _address(seller, instance.get("bg-5"),
             {"postcode": "bt-38", "line1": "bt-35", "city": "bt-37", "country": "bt-40"},
             "bg-5 (seller address)")
    if instance.get("bt-31"):
        reg = _sub(seller, _q(RAM, "SpecifiedTaxRegistration"))
        _sub(reg, _q(RAM, "ID"), str(instance["bt-31"]).replace(" ", "").upper(), schemeID="VA")
    buyer = _sub(agreement, _q(RAM, "BuyerTradeParty"))
    _sub(buyer, _q(RAM, "Name"), str(_require(instance, "bt-44", "buyer")))
    _address(buyer, instance.get("bg-8"),
             {"postcode": "bt-53", "line1": "bt-50", "city": "bt-52", "country": "bt-55"},
             "bg-8 (buyer address)")

    # --- header delivery -------------------------------------------------
    delivery = _sub(txn, _q(RAM, "ApplicableHeaderTradeDelivery"))
    event = _sub(delivery, _q(RAM, "ActualDeliverySupplyChainEvent"))
    occ = _sub(event, _q(RAM, "OccurrenceDateTime"))
    _sub(occ, _q(UDT, "DateTimeString"), iso_to_ccyyccmm(_require(instance, "bt-2", "document")), format="102")

    # --- header settlement ------------------------------------------------
    settlement = _sub(txn, _q(RAM, "ApplicableHeaderTradeSettlement"))
    _sub(settlement, _q(RAM, "InvoiceCurrencyCode"), str(_require(instance, "bt-5", "document")))

    means = instance.get("bg-16") or {}
    if means.get("bt-84") or means.get("bt-82"):
        pm = _sub(settlement, _q(RAM, "SpecifiedTradeSettlementPaymentMeans"))
        _sub(pm, _q(RAM, "TypeCode"), str(means.get("bt-82") or "58"))
        if means.get("bt-84"):
            acct = _sub(pm, _q(RAM, "PayeePartyCreditorFinancialAccount"))
            _sub(acct, _q(RAM, "IBANID"), str(means["bt-84"]).replace(" ", "").upper())
            if means.get("bt-86"):
                inst = _sub(pm, _q(RAM, "PayeeSpecifiedCreditorFinancialInstitution"))
                _sub(inst, _q(RAM, "BICID"), str(means["bt-86"]).replace(" ", "").upper())

    breakdown = instance.get("bg-23") or []
    if not breakdown:
        raise MissingFieldError("missing VAT breakdown (bg-23)")
    for cat in breakdown:
        tax = _sub(settlement, _q(RAM, "ApplicableTradeTax"))
        _sub(tax, _q(RAM, "CalculatedAmount"), fmt_amount(_require(cat, "bt-117", "bg-23")))
        _sub(tax, _q(RAM, "TypeCode"), "VAT")
        _sub(tax, _q(RAM, "BasisAmount"), fmt_amount(_require(cat, "bt-116", "bg-23")))
        _sub(tax, _q(RAM, "CategoryCode"), str(_require(cat, "bt-120", "bg-23")))
        _sub(tax, _q(RAM, "RateApplicablePercent"), fmt_amount(_require(cat, "bt-119", "bg-23")))

    if instance.get("bt-20") or instance.get("bt-9"):
        terms = _sub(settlement, _q(RAM, "SpecifiedTradePaymentTerms"))
        if instance.get("bt-20"):
            _sub(terms, _q(RAM, "Description"), str(instance["bt-20"]))
        if instance.get("bt-9"):
            due = _sub(terms, _q(RAM, "DueDateDateTime"))
            _sub(due, _q(UDT, "DateTimeString"), iso_to_ccyyccmm(instance["bt-9"]), format="102")

    totals = instance.get("bg-22") or {}
    summ = _sub(settlement, _q(RAM, "SpecifiedTradeSettlementHeaderMonetarySummation"))
    _sub(summ, _q(RAM, "LineTotalAmount"), fmt_amount(_require(totals, "bt-106", "bg-22")))
    _sub(summ, _q(RAM, "ChargeTotalAmount"), fmt_amount(totals.get("charge_total") or "0.00"))
    _sub(summ, _q(RAM, "AllowanceTotalAmount"), fmt_amount(totals.get("allowance_total") or "0.00"))
    _sub(summ, _q(RAM, "TaxBasisTotalAmount"), fmt_amount(_require(totals, "bt-109", "bg-22")))
    _sub(summ, _q(RAM, "TaxTotalAmount"), fmt_amount(_require(totals, "bt-110", "bg-22")),
         currencyID=str(_require(instance, "bt-5", "document")))
    _sub(summ, _q(RAM, "GrandTotalAmount"), fmt_amount(_require(totals, "bt-112", "bg-22")))
    prepaid = Decimal(fmt_amount(totals.get("bt-113") or "0.00"))
    _sub(summ, _q(RAM, "TotalPrepaidAmount"), fmt_amount(prepaid))
    _sub(summ, _q(RAM, "DuePayableAmount"), fmt_amount(_require(totals, "bt-115", "bg-22")))

    return ET.tostring(root, encoding="unicode")


def build_invoice_xml_document(instance: dict) -> str:
    """Same as build_invoice_xml but with an XML declaration and trailing newline."""
    body = build_invoice_xml(instance)
    return '<?xml version="1.0" encoding="utf-8"?>\n' + body + "\n"
