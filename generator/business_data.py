"""Deterministic business data for the synthetic corpus.

Pure stdlib. Every value is derived from a seed so that `xbench generate`
reproduces byte-identical ground truth. All companies, people, IBANs and VAT
ids are synthetic (fictional, checksum-valid where formats demand it).
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")

CITIES = [
    ("München", "80331"), ("Hamburg", "20359"), ("Berlin", "10115"), ("Köln", "50667"),
    ("Frankfurt am Main", "60311"), ("Stuttgart", "70173"), ("Düsseldorf", "40210"),
    ("Dresden", "01067"), ("Leipzig", "04109"), ("Nürnberg", "90402"),
    ("Bremen", "28195"), ("Hannover", "30159"), ("Münster", "48143"), ("Freiburg", "79098"),
]

STREETS = [
    "Bahnhofstraße", "Hauptstraße", "Lindenweg", "Am Sportplatz", "Kirchplatz",
    "Werkstraße", "Hafenstraße", "Domstraße", "Prager Straße", "Ammonstraße",
    "Rathausplatz", "Industriering", "Rosenstraße", "Mühlenweg", "Am Markt",
]

COMPANY_A = [
    "Süddeutsche Systemtechnik", "Nordlicht Logistik", "Verlag Rhein-Wissen",
    "Digitalberatung Elbtal", "Mediahn Precision", "Rheintal Anlagenbau",
    "Alpenhof Gebäudereinigung", "Spree Werkstätten", "Baltic Data Dienste",
    "Odenwald Elektrotechnik", "Kurpfalz Messtechnik", "Weserbergland Kunststoff",
    "Fichtelgebirge Werkzeuge", "Saarbrücken Druckzentrum", "Emsland Agrartechnik",
]

COMPANY_SUFFIX = ["GmbH", "GmbH & Co. KG", "AG", "e.K.", "GmbH"]

BUYER_B2B = [
    "Medienhaus Elbtal", "Hanseatische Versandhandel", "Schwaben Metallbau",
    "Klinikum Musterstadt", "Gastronomie-Großhandel Westerwald", "Fraunhofer-artige Institutsteile",
    "Kanzlei Berger & Partner", "Treuhand Rhein-Main", "Autohaus am Stadtpark",
    "Facility Management Hessen", "Großküchen Nord", "Textilreinigung Bayern",
]

BUYER_B2G = [
    "Stadtwerke Musterstadt AöR", "Universitätsverwaltung Musterstadt",
    "Gemeinde Verwaltungsgemeinschaft Altbachtal", "Landratsamt Musterkreis",
    "Polizeipräsidium Musterhausen", "Bundeswehr-Dienstleistungszentrum Musterort",
]

ITEMS = {
    "it-services": [
        ("Entwicklungsleistung API-Integration", "HUR", Decimal("85"), Decimal("150")),
        ("Managed Hosting Premium (12 Monate)", "MON", Decimal("35"), Decimal("480")),
        ("Schulung XRechnung", "HUR", Decimal("95"), Decimal("150")),
        ("IT-Security-Audit", "HUR", Decimal("110"), Decimal("160")),
        ("Support-Pauschale quartalsweise", "MON", Decimal("60"), Decimal("240")),
        ("Lizenz Invoice-Tool (Jahreslizenz)", "MON", Decimal("180"), Decimal("240")),
    ],
    "books-print": [
        ("Fachbuch XRechnung-Spezifikation", "C62", Decimal("24"), Decimal("39.90")),
        ("Handbuch EN 16931 (Print)", "C62", Decimal("15"), Decimal("24.50")),
        ("Druck Layout-Handbuch", "C62", Decimal("8"), Decimal("12.80")),
        ("Broschüre Pflichtangaben", "C62", Decimal("3.50"), Decimal("6.90")),
    ],
    "consulting": [
        ("Beratung Data-Migration", "HUR", Decimal("75"), Decimal("95")),
        ("Prozessanalyse Rechnungseingang", "HUR", Decimal("80"), Decimal("110")),
        ("Workshop GoBD-Compliance", "HUR", Decimal("120"), Decimal("180")),
        ("Zwischenbericht Projektphase 2", "C62", Decimal("400"), Decimal("1200")),
    ],
    "craft": [
        ("Elektroinstallation Wartung", "HUR", Decimal("55"), Decimal("78")),
        ("Material Schaltschrank", "C62", Decimal("120"), Decimal("340")),
        ("Anfahrtspauschale", "C62", Decimal("25"), Decimal("45")),
        ("Sonnenschutz Montage", "HUR", Decimal("48"), Decimal("65")),
    ],
}

SECTORS = list(ITEMS.keys())

FIRST_NAMES = ["Anna", "Jonas", "Klara", "Felix", "Marie", "Lukas", "Hanna", "Paul",
               "Sophie", "Maximilian", "Emma", "Tobias", "Lena", "Niklas"]
LAST_NAMES = ["Weber", "Schneider", "Hoffmann", "Fischer", "Wagner", "Becker",
              "Schulz", "Richter", "Koch", "Bauer", "Wolf", "Neumann"]

CONTACT_NOTE = [
    "Bei Rückfragen: %s %s, Telefon %s",
    "Ansprechpartner: %s %s (%s)",
    "Erreichbar Mo-Fr 9-16 Uhr: %s %s",
]


def _fmt_iban(rng: random.Random) -> str:
    """Synthetic but mod-97 checksum-valid German IBAN."""
    bank = "".join(rng.choice("0123456789") for _ in range(8))
    acct = "".join(rng.choice("0123456789") for _ in range(10))
    s = bank + acct + "131400"  # "DE" -> 1314, check digits "00"
    check = 98 - (int(s) % 97)
    return "DE%02d%s%s" % (check, bank, acct)


def _address(rng: random.Random) -> dict:
    city, postcode = rng.choice(CITIES)
    return {"street": "%s %d" % (rng.choice(STREETS), rng.randint(1, 120)), "city": city, "zip": postcode}


def build_iban(rng: random.Random) -> str:
    return _fmt_iban(rng)


def _display(instance: dict, number_format: str, date_format: str) -> None:
    """Attach human-facing display hints (layout rendering only — never scored)."""
    pass  # display formatting happens in render.py from layout params


def make_business_case(seed: int, variant: int, layout: dict) -> dict:
    """Deterministic EN 16931 subset instance (schema.json shape) + meta axes.

    variant 0: standard B2B, 19% VAT
    variant 1: B2G buyer with Leitweg-ID, 7% VAT
    variant 2: mixed 19%+7%; layouts flagged credit_note produce a 381 credit note
    """
    rng = random.Random(seed)
    sector = layout["sector"]
    catalog = ITEMS[sector]
    seller_name = rng.choice(COMPANY_A) + " " + rng.choice(COMPANY_SUFFIX)
    seller_addr = _address(rng)
    seller_vat = "DE" + "".join(rng.choice("0123456789") for _ in range(9))

    is_b2g = variant == 1
    buyer_pool = BUYER_B2G if is_b2g else BUYER_B2B
    buyer_name = rng.choice(buyer_pool) + ("" if is_b2g else " " + rng.choice(COMPANY_SUFFIX))
    buyer_addr = _address(rng)

    doc_type = "380"
    sign = Decimal("1")
    if variant == 2 and layout.get("credit_note"):
        doc_type = "381"
        sign = Decimal("-1")

    # VAT regimes
    if variant == 0:
        rate_pool = [Decimal("19")]
    elif variant == 1:
        rate_pool = [Decimal("7")]
    else:
        rate_pool = [Decimal("19"), Decimal("7")]
    n_lines = rng.randint(2, 5)
    rates = [rng.choice(rate_pool) for _ in range(n_lines)]

    issue = date(2025, 9, 1) + timedelta(days=rng.randint(0, 420))
    due_days = rng.choice([14, 14, 14, 30])
    due = issue + timedelta(days=due_days)
    payment_terms = "Zahlbar innerhalb von %d Tagen" % due_days
    if is_b2g:
        leitweg = "%05d-%05d-%d" % (rng.randint(5000, 5999), rng.randint(10000, 99999), rng.randint(1, 99))
        buyer_ref = leitweg
    else:
        buyer_ref = "%s-%d-%s" % (rng.choice(["AUFTRAG", "KUNDENREF", "BEST-2026"]), rng.randint(100, 9999),
                                  rng.choice(["A", "B", "C"]))

    lines, bases = [], {}
    for i in range(n_lines):
        name, unit, lo, hi = catalog[rng.randrange(len(catalog))]
        if unit in ("HUR", "MON"):
            qty = Decimal(rng.randint(2, 40))
        else:
            qty = Decimal(rng.randint(1, 25))
        price = (lo + (hi - lo) * Decimal(rng.randint(0, 100)) / Decimal("100")).quantize(CENT)
        net = (qty * price).quantize(CENT, rounding=ROUND_HALF_UP) * sign
        rate = rates[i]
        lines.append({
            "bt-126": str(i + 1),
            "bt-153": name,
            "bt-129": str(int(qty) if qty == qty.to_integral() else qty),
            "bt-130": unit,
            "bt-146": fmt_amount(price),
            "bt-131": fmt_amount(net),
            "bt-151": "S",
            "bt-152": fmt_amount(rate),
        })
        key = str(rate)
        bases[key] = bases.get(key, Decimal("0")) + net

    breakdown = []
    for rate in sorted(bases, key=Decimal):
        base = bases[rate]
        vat = (base * Decimal(rate) / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP) * sign
        breakdown.append({
            "bt-120": "S",
            "bt-116": fmt_amount(base),
            "bt-117": fmt_amount(vat),
            "bt-119": fmt_amount(Decimal(rate)),
        })
    bt106 = fmt_amount(sum(Decimal(l["bt-131"]) for l in lines))
    bt110 = fmt_amount(sum(Decimal(b["bt-117"]) for b in breakdown))
    bt109 = bt106
    bt112 = fmt_amount(Decimal(bt109) + Decimal(bt110))
    bt115 = bt112

    instance = {
        "bt-1": "RE-%s-%04d" % (issue.year, rng.randint(1, 9999)),
        "bt-2": issue.isoformat(),
        "bt-3": doc_type,
        "bt-5": "EUR",
        "bt-9": due.isoformat(),
        "bt-10": buyer_ref,
        "bt-20": payment_terms,
        "bt-27": seller_name,
        "bg-5": {"bt-35": seller_addr["street"], "bt-37": seller_addr["city"],
                 "bt-38": seller_addr["zip"], "bt-40": "DE"},
        "bt-31": seller_vat,
        "bt-44": buyer_name,
        "bg-8": {"bt-50": buyer_addr["street"], "bt-52": buyer_addr["city"],
                 "bt-53": buyer_addr["zip"], "bt-55": "DE"},
        "bt-48": None,
        "bg-16": {"bt-82": "58", "bt-84": _fmt_iban(rng),
                  "bt-86": rng.choice(["COBADEFFXXX", "PBNKDEFFXXX", "BYLADEM1001", "HELADEFKFRA"])},
        "bg-25": lines,
        "bg-23": breakdown,
        "bg-22": {"bt-106": bt106, "bt-109": bt109, "bt-110": bt110,
                  "bt-112": bt112, "bt-113": None, "bt-115": bt115},
    }
    meta = {
        "doc_type": doc_type,
        "vat_regime": {0: "standard19", 1: "reduced7-b2g", 2: "mixed"}[variant],
        "buyer_ref_kind": "leitweg-id" if is_b2g else "generic",
        "date_ambiguous": issue.day <= 12,
        "credit_note": doc_type == "381",
    }
    return {"instance": instance, "meta": meta}


def fmt_amount(d: Decimal) -> str:
    return str(d.quantize(CENT, rounding=ROUND_HALF_UP))
