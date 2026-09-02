#!/usr/bin/env python3
"""Génère les icônes PWA de SimuPoke (PNG, stdlib pure — aucun binaire versionné).

Dessine une Poké Ball stylisée dans la palette du projet (navire nocturne + or
Champions) et l'encode en PNG RGBA à la main (zlib). Appelé par
`build_pyodide.py` ; produit `icon-192.png` et `icon-512.png` dans un dossier.

    python scripts/gen_icons.py <outdir>
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

# Palette (RGBA)
NAVY = (14, 20, 27, 255)      # fond
AMBER = (240, 180, 41, 255)   # moitié haute
LIGHT = (230, 237, 243, 255)  # moitié basse
BAND = (10, 15, 20, 255)      # bande centrale + contour


def _png(width: int, height: int, buf: bytearray) -> bytes:
    def chunk(typ: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filtre 0 (None)
        raw.extend(buf[y * stride:(y + 1) * stride])
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def _render(n: int) -> bytes:
    cx = cy = (n - 1) / 2.0
    R = n * 0.34          # rayon de la balle
    band = n * 0.05       # demi-hauteur de la bande
    ring = n * 0.13       # rayon du bouton (contour)
    dot = n * 0.075       # rayon du bouton (centre)
    buf = bytearray(n * n * 4)
    for y in range(n):
        for x in range(n):
            dx, dy = x - cx, y - cy
            d = (dx * dx + dy * dy) ** 0.5
            if d <= dot:
                c = AMBER
            elif d <= ring:
                c = BAND
            elif d <= R:
                if abs(dy) <= band:
                    c = BAND
                elif dy < 0:
                    c = AMBER
                else:
                    c = LIGHT
            else:
                c = NAVY
            i = (y * n + x) * 4
            buf[i:i + 4] = bytes(c)
    return _png(n, n, buf)


def make_icons(outdir: str | Path) -> list[Path]:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for size in (192, 512):
        p = out / f"icon-{size}.png"
        p.write_bytes(_render(size))
        written.append(p)
    return written


if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else "."
    for p in make_icons(dest):
        print(f"Écrit {p} ({p.stat().st_size} o).")
