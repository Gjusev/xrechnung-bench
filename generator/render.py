"""Rendering layer (optional dependencies).

render_pdf: digital-native invoice PDF via reportlab — raises RenderUnavailable
with install hint when reportlab is absent. render_png: scan-simulated page
image drawn with Pillow — raises RenderUnavailable when Pillow is absent.

Both renderers are layout-parameterized so the 30 layout families produce
visually distinct invoices from identical business data.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path


class RenderUnavailable(Exception):
    """Raised when the optional rendering dependency is not installed."""


def _fmt_money(value: str | Decimal, number_format: str) -> str:
    d = Decimal(str(value))
    s = "{:,.2f}".format(d)
    if number_format == "de":
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s + " EUR"


def _fmt_date(iso: str, date_format: str) -> str:
    y, m, d = iso.split("-")
    if date_format == "de":
        return "%s.%s.%s" % (d, m, y)
    if date_format == "us-like":
        return "%s/%s/%s" % (m, d, y)
    return iso


def render_pdf(instance: dict, layout: dict, path: str | Path) -> None:
    """Digital-native PDF (T0 source artifact). Requires reportlab."""
    try:
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.pdfgen import canvas  # type: ignore
    except ImportError as exc:
        raise RenderUnavailable(
            "render_pdf needs the optional 'reportlab' package (pip install reportlab) — "
            "offline environment skips PDF rendering and records it in the manifest."
        ) from exc

    width, height = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    style = layout
    margin = 46
    y = height - margin

    c.setFont(style["font_name"], style["font_size"])
    c.drawString(margin, y, instance["bt-27"])
    y -= style["line_height"]
    c.setFont(style["font_name"], style["font_size"] - 2)
    bg5 = instance["bg-5"]
    c.drawString(margin, y, "%s, %s %s" % (bg5["bt-35"], bg5["bt-38"], bg5["bt-37"]))
    y -= style["line_height"]
    c.drawString(margin, y, "USt-IdNr.: %s" % instance["bt-31"])
    y -= style["line_height"] * 2

    c.setFont(style["font_name"], style["font_size"])
    c.drawString(margin, y, instance["bt-44"])
    bg8 = instance["bg-8"]
    y -= style["line_height"]
    c.setFont(style["font_name"], style["font_size"] - 2)
    c.drawString(margin, y, "%s, %s %s" % (bg8["bt-50"], bg8["bt-53"], bg8["bt-52"]))
    y -= style["line_height"]
    c.drawString(margin, y, "Kundenreferenz: %s" % instance["bt-10"])
    y -= style["line_height"] * 2

    nf, df = style["number_format"], style["date_format"]
    meta_x = width - margin - 190
    c.setFont(style["font_name"], style["font_size"])
    for label, value in (("Rechnungsnummer:", instance["bt-1"]),
                         ("Rechnungsdatum:", _fmt_date(instance["bt-2"], df)),
                         ("Fällig am:", _fmt_date(instance["bt-9"], df))):
        c.drawString(meta_x, y, label)
        c.drawString(meta_x + 110, y, str(value))
        y -= style["line_height"]
    y -= style["line_height"]

    if style["header_rule"]:
        c.line(margin, y, width - margin, y)
        y -= style["line_height"]

    c.setFont(style["font_name"], style["font_size"] - 1)
    c.drawString(margin, y, "Pos.")
    c.drawString(margin + 40, y, "Beschreibung")
    c.drawString(width - margin - 200, y, "Menge")
    c.drawString(width - margin - 130, y, "Einzel")
    c.drawString(width - margin - 60, y, "Netto")
    y -= style["line_height"]
    if style["table_rules"]:
        c.line(margin, y, width - margin, y)
    y -= style["line_height"] * 0.6

    for ln in instance["bg-25"]:
        c.drawString(margin, y, ln["bt-126"])
        c.drawString(margin + 40, y, ln["bt-153"][:58])
        c.drawString(width - margin - 200, y, "%s %s" % (ln["bt-129"], ln["bt-130"]))
        c.drawString(width - margin - 130, y, _fmt_money(ln["bt-146"], nf))
        c.drawString(width - margin - 60, y, _fmt_money(ln["bt-131"], nf))
        y -= style["line_height"]
    y -= style["line_height"] * 0.5

    t = instance["bg-22"]
    for label, key in (("Summe netto", "bt-106"), ("Umsatzsteuer gesamt", "bt-110"),
                       ("Gesamt brutto", "bt-112"), ("Fälliger Betrag", "bt-115")):
        c.drawString(meta_x, y, label)
        c.drawString(width - margin - 60 - c.stringWidth(_fmt_money(t[key], nf), style["font_name"],
                                                         style["font_size"] - 1), y,
                     _fmt_money(t[key], nf))
        y -= style["line_height"]
    y -= style["line_height"] * 0.5
    for b in instance["bg-23"]:
        c.setFont(style["font_name"], style["font_size"] - 2)
        c.drawString(meta_x, y, "zzgl. %s%% USt auf %s" % (b["bt-119"], _fmt_money(b["bt-116"], nf)))
        y -= style["line_height"]
    c.setFont(style["font_name"], style["font_size"] - 2)
    y -= style["line_height"]
    c.drawString(margin, y, "%s — IBAN %s, BIC %s" % (instance["bt-20"],
                                                      instance["bg-16"]["bt-84"],
                                                      instance["bg-16"]["bt-86"]))
    c.save()


def render_png(instance: dict, layout: dict, path: str | Path, dpi: int = 200,
               width_px: int = 1654, height_px: int = 2339) -> None:
    """Scan-simulated page image (input for degrade + models). Requires Pillow."""
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except ImportError as exc:
        raise RenderUnavailable(
            "render_png needs the optional 'Pillow' package (pip install pillow) — "
            "offline environment skips image rendering and records it in the manifest."
        ) from exc

    img = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(img)
    margin = int(width_px * 0.07)
    y = margin
    lh = int(layout["font_size"] * dpi / 72) + 8

    def text(x, s, size=layout["font_size"]):
        nonlocal y
        draw.text((x, y), s, fill=(20, 20, 20))
        y += int(size * dpi / 72) + 6

    text(margin, instance["bt-27"])
    bg5 = instance["bg-5"]
    text(margin, "%s, %s %s" % (bg5["bt-35"], bg5["bt-38"], bg5["bt-37"]), layout["font_size"] - 1)
    text(margin, "USt-IdNr.: %s" % instance["bt-31"], layout["font_size"] - 1)
    y += lh
    text(margin, instance["bt-44"])
    bg8 = instance["bg-8"]
    text(margin, "%s, %s %s" % (bg8["bt-50"], bg8["bt-53"], bg8["bt-52"]), layout["font_size"] - 1)
    text(margin, "Kundenreferenz: %s" % instance["bt-10"], layout["font_size"] - 1)
    y += lh
    nf, df = layout["number_format"], layout["date_format"]
    meta_x = width_px - margin - 480
    for label, value in (("Rechnungsnummer:", instance["bt-1"]),
                         ("Rechnungsdatum:", _fmt_date(instance["bt-2"], df)),
                         ("Faellig am:", _fmt_date(instance["bt-9"], df))):
        draw.text((meta_x, y), label, fill=(20, 20, 20))
        draw.text((meta_x + 220, y), str(value), fill=(20, 20, 20))
        y += lh
    if layout["header_rule"]:
        draw.line((margin, y, width_px - margin, y), fill=(60, 60, 60), width=2)
        y += lh
    text(margin, "Pos.  Beschreibung                                    Menge         Einzel          Netto",
         layout["font_size"] - 1)
    for ln in instance["bg-25"]:
        text(margin, "%s   %-46s %s %s   %s   %s" % (
            ln["bt-126"], ln["bt-153"][:44], ln["bt-129"], ln["bt-130"],
            _fmt_money(ln["bt-146"], nf), _fmt_money(ln["bt-131"], nf)), layout["font_size"] - 1)
    y += int(lh * 0.5)
    t = instance["bg-22"]
    for label, key in (("Summe netto", "bt-106"), ("Umsatzsteuer gesamt", "bt-110"),
                       ("Gesamt brutto", "bt-112"), ("Faelliger Betrag", "bt-115")):
        draw.text((meta_x, y), label, fill=(20, 20, 20))
        draw.text((width_px - margin - 160, y), _fmt_money(t[key], nf), fill=(20, 20, 20))
        y += lh
    y += int(lh * 0.5)
    for b in instance["bg-23"]:
        text(meta_x, "zzgl. %s%% USt auf %s" % (b["bt-119"], _fmt_money(b["bt-116"], nf)),
             layout["font_size"] - 2)
    text(margin, "%s - IBAN %s, BIC %s" % (instance["bt-20"], instance["bg-16"]["bt-84"],
                                           instance["bg-16"]["bt-86"]), layout["font_size"] - 2)
    img.save(str(path), "PNG")
