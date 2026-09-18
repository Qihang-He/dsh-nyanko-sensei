#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Review sheets for the motion animations.

Judging an animation from a single frame is impossible and judging it from a
video requires playing it, so this lays every frame of an animation out in a
row. Squash, timing and grounding mistakes are all obvious at a glance, and the
whole set can be compared in one image.

Usage:
    python motion_sheet.py                    # every animation
    python motion_sheet.py idle hop           # selected ones
    python motion_sheet.py --cols 8
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
FRAMES = ROOT / "work" / "motion"
OUT = ROOT / "work" / "motion-review"
PANEL = (32, 34, 40)
LABEL = 20


def sheet_for(name: str, cols: int, cell: int = 128) -> Path | None:
    files = sorted((FRAMES / name).glob("*.png"))
    if not files:
        return None
    rows = max(1, (len(files) + cols - 1) // cols)
    width = cell * min(cols, len(files))
    image = Image.new("RGB", (width, LABEL + (cell + LABEL) * rows), (18, 18, 22))
    draw = ImageDraw.Draw(image)

    for index, path in enumerate(files):
        sprite = Image.open(path).convert("RGBA").resize((cell, cell), Image.LANCZOS)
        panel = Image.new("RGBA", (cell, cell), PANEL + (255,))
        panel.alpha_composite(sprite)
        x = (index % cols) * cell
        y = LABEL + (index // cols) * (cell + LABEL)
        image.paste(panel.convert("RGB"), (x, y))
        draw.rectangle([x, y, x + cell - 1, y + cell - 1], outline=(70, 70, 78))
        draw.text((x + 6, y + cell + 4), f"f{index:02d}", fill=(170, 170, 178))

    draw.text((6, 5), name, fill=(235, 235, 240))
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{name}.png"
    image.save(out)
    return out


def main() -> None:
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    cols = 8
    if "--cols" in sys.argv:
        cols = int(sys.argv[sys.argv.index("--cols") + 1])

    names = argv or sorted(p.name for p in FRAMES.iterdir() if p.is_dir())
    if not names:
        raise SystemExit(f"no rendered motion frames in {FRAMES}")

    for name in names:
        out = sheet_for(name, cols)
        if out is None:
            print(f"  {name:16s} (no frames)")
        else:
            print(f"  {out.relative_to(ROOT)}")
    print(f"\nreview sheets in {OUT}")


if __name__ == "__main__":
    main()
