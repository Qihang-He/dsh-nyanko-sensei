#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Overlay a labelled coordinate grid on a reference still.

Tuning a crop or a mask by guessing numbers and re-running is slow and, worse,
it hides which part of the image a parameter is actually affecting. Drawing the
grid once turns the tuning into reading coordinates off the picture.

The grid is in fractions of width and height, which is the unit the extractor's
`crop` setting uses, so a value read off this image goes straight into the code.

Usage:
    python grid_overlay.py "OIP-C (2)"          # -> work/extracted/<name>-grid.png
    python grid_overlay.py --all
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "work" / "ref"
OUT = ROOT / "work" / "extracted"
STEPS = 10


def overlay(path: Path) -> Path:
    image = Image.open(path).convert("RGB")
    # Enlarge so the fine lines and the subject edge are both readable.
    scale = max(1, int(900 / max(image.size)))
    if scale > 1:
        image = image.resize((image.width * scale, image.height * scale), Image.LANCZOS)
    width, height = image.size
    draw = ImageDraw.Draw(image)

    for index in range(STEPS + 1):
        fraction = index / STEPS
        x = int(fraction * (width - 1))
        y = int(fraction * (height - 1))
        colour = (255, 60, 60) if index % 5 == 0 else (255, 200, 60)
        draw.line([(x, 0), (x, height)], fill=colour, width=1)
        draw.line([(0, y), (width, y)], fill=colour, width=1)
        draw.text((x + 3, 4), f"{fraction:.1f}", fill=colour)
        draw.text((4, y + 3), f"{fraction:.1f}", fill=colour)

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{path.stem}-grid.png"
    image.save(out)
    return out


def main() -> None:
    argv = sys.argv[1:]
    if "--all" in argv or not argv:
        targets = sorted(p for p in REFS.iterdir()
                         if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    else:
        targets = []
        for name in argv:
            match = next((p for p in REFS.iterdir() if p.stem == name), None)
            if match:
                targets.append(match)
            else:
                print(f"  ! {name}: not found in {REFS}")
    for path in targets:
        print(f"  {overlay(path).relative_to(ROOT)}")


if __name__ == "__main__":
    main()
