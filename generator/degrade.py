"""Difficulty tiers & degradation transforms.

Tier T0: digital-native render, untouched.
Tier T1: office scan — 200 DPI, +-0.5 deg rotation, mild noise, JPEG 85.
Tier T2: bad scan — 96-150 DPI, +-1.5-3 deg rotation, Gaussian noise, low contrast, JPEG 60-75.
Tier T3: worst case — T2 plus stamps/overlaps over amount/date regions, warp.

Implementation: pure-python path (stdlib only) operates on raw RGB pixel
buffers and writes PNG via zlib; it works everywhere. When Pillow is
available a fast path is used and JPEG compression (a Pillow-only operation)
becomes available — without Pillow the JPEG step is SKIPPED and recorded as
`jpeg_skipped_no_pil`, never silently ignored.
"""
from __future__ import annotations

import math
import random
import struct
import zlib
from pathlib import Path

TIERS = ["T0", "T1", "T2", "T3"]


class Img:
    """Raw RGB image: width, height, flat bytes (3 per pixel)."""

    def __init__(self, width: int, height: int, pixels: bytes):
        if len(pixels) != width * height * 3:
            raise ValueError("pixel buffer size mismatch")
        self.w, self.h, self.pixels = width, height, pixels


# ---------------------------------------------------------------------------
# pure-python PNG codec (8-bit RGB, no interlace; our own files only)
# ---------------------------------------------------------------------------

def png_write(path: str | Path, img: Img) -> None:
    raw = bytearray()
    stride = img.w * 3
    for y in range(img.h):
        raw.append(0)  # filter type 0 (None) per scanline
        raw += img.pixels[y * stride:(y + 1) * stride]
    idat = zlib.compress(bytes(raw), 6)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", img.w, img.h, 8, 2, 0, 0, 0)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(chunk(b"IHDR", ihdr))
        fh.write(chunk(b"IDAT", idat))
        fh.write(chunk(b"IEND", b""))


def png_read(path: str | Path) -> Img:
    with open(path, "rb") as fh:
        data = fh.read()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG file")
    pos, width, height, bit_depth, color_type = 8, 0, 0, 8, 2
    idat = bytearray()
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        if tag == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", payload[:10])
        elif tag == b"IDAT":
            idat += payload
        elif tag == b"IEND":
            break
        pos += 12 + length
    if bit_depth != 8 or color_type != 2:
        raise ValueError("pure-python reader supports 8-bit RGB PNGs only (written by png_write)")
    rawdata = zlib.decompress(bytes(idat))
    stride = width * 3
    out = bytearray(width * height * 3)
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        ftype = rawdata[pos]
        line = bytearray(rawdata[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if ftype == 1:  # Sub
            for i in range(3, stride):
                line[i] = (line[i] + line[i - 3]) & 0xFF
        elif ftype == 2:  # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:  # Average
            for i in range(stride):
                left = line[i - 3] if i >= 3 else 0
                line[i] = (line[i] + (left + prev[i]) // 2) & 0xFF
        elif ftype == 4:  # Paeth
            for i in range(stride):
                a = line[i - 3] if i >= 3 else 0
                b = prev[i]
                c = prev[i - 3] if i >= 3 else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return Img(width, height, bytes(out))


# ---------------------------------------------------------------------------
# transforms (pure python)
# ---------------------------------------------------------------------------

def add_noise(img: Img, rng: random.Random, sigma: int = 18) -> Img:
    """Additive Gaussian-ish noise (sum of uniforms ~ bell curve, deterministic)."""
    px = bytearray(img.pixels)
    for i in range(len(px)):
        n = rng.randint(-sigma, sigma) + rng.randint(-sigma, sigma)
        v = px[i] + n
        px[i] = 0 if v < 0 else (255 if v > 255 else v)
    return Img(img.w, img.h, bytes(px))


def rotate(img: Img, degrees: float, fill: int = 245) -> Img:
    """Nearest-neighbour rotation about the centre; canvas grows to fit."""
    rad = math.radians(degrees)
    cos, sin = math.cos(rad), -math.sin(rad)
    w2, h2 = img.w / 2.0, img.h / 2.0
    corners = [(-w2, -h2), (w2, -h2), (-w2, h2), (w2, h2)]
    xs = [x * cos - y * sin for x, y in corners]
    ys = [x * sin + y * cos for x, y in corners]
    nw, nh = int(math.ceil(max(xs) - min(xs))), int(math.ceil(max(ys) - min(ys)))
    nw2, nh2 = nw / 2.0, nh / 2.0
    out = bytearray([fill]) * (nw * nh * 3)
    src = img.pixels
    for oy in range(nh):
        dy = oy - nh2 + 0.5
        for ox in range(nw):
            dx = ox - nw2 + 0.5
            sx = dx * cos + dy * sin + w2
            sy = -dx * sin + dy * cos + h2
            if 0 <= sx < img.w and 0 <= sy < img.h:
                si = (int(sy) * img.w + int(sx)) * 3
                di = (oy * nw + ox) * 3
                out[di:di + 3] = src[si:si + 3]
    return Img(nw, nh, bytes(out))


def downscale(img: Img, factor: float) -> Img:
    """Box-filter downscale by a fractional factor (simulates low DPI)."""
    nw = max(1, int(img.w / factor))
    nh = max(1, int(img.h / factor))
    out = bytearray(nw * nh * 3)
    src = img.pixels
    for oy in range(nh):
        y0, y1 = int(oy * factor), max(int((oy + 1) * factor), int(oy * factor) + 1)
        for ox in range(nw):
            x0, x1 = int(ox * factor), max(int((ox + 1) * factor), int(ox * factor) + 1)
            r = g = b = n = 0
            for sy in range(y0, min(y1, img.h)):
                for sx in range(x0, min(x1, img.w)):
                    i = (sy * img.w + sx) * 3
                    r += src[i]; g += src[i + 1]; b += src[i + 2]; n += 1
            di = (oy * nw + ox) * 3
            out[di], out[di + 1], out[di + 2] = r // n, g // n, b // n
    return Img(nw, nh, bytes(out))


def adjust_contrast(img: Img, gain: float = 0.7, bias: float = 70) -> Img:
    """Low-contrast print: v' = v*gain + bias."""
    table = bytearray(256)
    for v in range(256):
        nv = int(v * gain + bias)
        table[v] = 0 if nv < 0 else (255 if nv > 255 else nv)
    px = bytes(table[img.pixels[i]] for i in range(len(img.pixels)))
    return Img(img.w, img.h, px)


def stamp_overlay(img: Img, rng: random.Random, box: tuple[int, int, int, int]) -> Img:
    """Approximate a rubber stamp: dark translucent rounded box + text bars,
    placed over the given box (used over amount/date regions in T3)."""
    x0, y0, x1, y1 = box
    x0 = max(0, x0); y0 = max(0, y0)
    x1 = min(img.w - 1, x1); y1 = min(img.h - 1, y1)
    px = bytearray(img.pixels)
    alpha = 0.45
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            border = (x in (x0, x1)) or (y in (y0, y1))
            bars = ((y - y0) * 7 // max(1, (y1 - y0))) % 2 == 0 and (x0 + 4) < x < (x1 - 4)
            if border or bars:
                i = (y * img.w + x) * 3
                px[i] = int(px[i] * (1 - alpha) + 90 * alpha)
                px[i + 1] = int(px[i + 1] * (1 - alpha) + 40 * alpha)
                px[i + 2] = int(px[i + 2] * (1 - alpha) + 60 * alpha)
    return Img(img.w, img.h, bytes(px))


# ---------------------------------------------------------------------------
# Pillow fast path
# ---------------------------------------------------------------------------

def _pillow():
    try:
        from PIL import Image  # type: ignore
        return Image
    except ImportError:
        return None


def to_pillow(img: Img):
    Image = _pillow()
    if Image is None:
        return None
    return Image.frombytes("RGB", (img.w, img.h), img.pixels)


def from_pillow(pil_image) -> Img:
    return Img(pil_image.width, pil_image.height, pil_image.convert("RGB").tobytes())


def apply_tier(img: Img, tier: str, seed: int, dpi_scale: float = 1.0) -> tuple[Img, list[str]]:
    """Apply the tier pipeline deterministically. Returns (image, step log)."""
    rng = random.Random(seed)
    steps: list[str] = []
    out = img

    if tier == "T0":
        steps.append("t0_untouched")
        return out, steps

    if tier == "T1":
        out = downscale(out, max(1.0, 1.5 * dpi_scale))
        steps.append("downscale_200dpi")
        out = rotate(out, rng.choice([-1, 1]) * rng.uniform(0.2, 0.5))
        steps.append("rotate_+-0.5deg")
        out = add_noise(out, rng, sigma=8)
        steps.append("noise_sigma8")
    elif tier == "T2":
        out = downscale(out, max(1.0, rng.choice([2.0, 2.5, 3.1]) * dpi_scale))
        steps.append("downscale_96-150dpi")
        out = rotate(out, rng.choice([-1, 1]) * rng.uniform(1.5, 3.0))
        steps.append("rotate_+-1.5-3deg")
        out = add_noise(out, rng, sigma=16)
        steps.append("noise_sigma16")
        out = adjust_contrast(out, gain=0.75, bias=55)
        steps.append("low_contrast")
    elif tier == "T3":
        out = downscale(out, max(1.0, rng.choice([2.5, 3.1]) * dpi_scale))
        steps.append("downscale_96dpi")
        out = rotate(out, rng.choice([-1, 1]) * rng.uniform(2.0, 3.0))
        steps.append("rotate_+-2-3deg")
        out = add_noise(out, rng, sigma=20)
        steps.append("noise_sigma20")
        out = adjust_contrast(out, gain=0.65, bias=65)
        steps.append("low_contrast")
        # stamps over amounts / dates regions (bottom-right totals block,
        # top-right date block) — coordinates in degraded-image space
        w, h = out.w, out.h
        out = stamp_overlay(out, rng, (int(w * 0.55), int(h * 0.70), int(w * 0.95), int(h * 0.80)))
        steps.append("stamp_over_totals")
        out = stamp_overlay(out, rng, (int(w * 0.60), int(h * 0.08), int(w * 0.95), int(h * 0.16)))
        steps.append("stamp_over_date_block")
    else:
        raise ValueError("unknown tier %r" % tier)

    if _pillow() is not None:
        quality = {"T1": 85, "T2": rng.choice([60, 68, 75]), "T3": rng.choice([55, 60])}[tier]
        steps.append("jpeg_q%d" % quality)  # applied by caller via save_jpeg
    else:
        steps.append("jpeg_skipped_no_pil")
    return out, steps


def save_jpeg(img: Img, path: str | Path, quality: int) -> bool:
    """JPEG needs Pillow; returns False (caller records skipped) if absent."""
    pil = to_pillow(img)
    if pil is None:
        return False
    pil.save(str(path), "JPEG", quality=quality)
    return True
