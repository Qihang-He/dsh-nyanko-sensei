#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Triage a folder of downloaded images down to usable character art.

The search stage produced hundreds of files with no metadata and no transparency.
Reviewing them by hand is the wrong use of attention, and reviewing them with a
vision model needs a credential this machine does not have.

What is left is the character's own appearance, which is unusually distinctive
and therefore a good filter. A calico cat that is mostly white with an orange
patch and a grey patch has a colour histogram that almost nothing else shares:
high cream/white coverage, meaningful orange and grey, and almost no green or
blue. Grass backgrounds, wooden interiors, blue skies, screenshots with UI
chrome and text-heavy pages all fail at least one of those.

So this ranks by that fingerprint and writes contact sheets of the best
candidates, which turns "look at 529 images" into "look at two sheets".

Usage:
    python triage_art.py                 # score, rank, write sheets
    python triage_art.py --top 96 --cols 12
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
# The search stage writes its downloads into `tmp/`; `raw/` is where the
# verified shortlist is supposed to land when that stage completes, so both are
# scanned and whichever holds files wins.
RAW_CANDIDATES = [
    ROOT / "work" / "search" / "raw",
    ROOT / "work" / "search" / "tmp",
]
OUT = ROOT / "work" / "triage"

EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def source_dir() -> Path:
    """The download directory that actually has images in it."""
    for directory in RAW_CANDIDATES:
        if directory.is_dir() and any(p.suffix.lower() in EXTS for p in directory.iterdir()):
            return directory
    raise SystemExit("no downloaded images in " + " or ".join(str(d) for d in RAW_CANDIDATES))


def classify(path: Path, sample: int = 256) -> dict | None:
    """Colour-composition fingerprint for one image."""
    try:
        image = Image.open(path).convert("RGB")
    except Exception:  # noqa: BLE001 - a corrupt download is simply skipped
        return None
    width, height = image.size
    if min(width, height) < 200:
        return None
    # Downsample: the fingerprint is a proportion, so a 256px thumbnail answers
    # it just as well and this runs over hundreds of files.
    image = image.resize((sample, sample), Image.LANCZOS)
    arr = np.asarray(image).astype(np.float32)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    maximum = np.maximum(np.maximum(r, g), b)
    minimum = np.minimum(np.minimum(r, g), b)
    sat = np.where(maximum > 1e-6, (maximum - minimum) / np.maximum(maximum, 1e-6), 0.0)
    total = arr.shape[0] * arr.shape[1]

    cream = (maximum > 190) & (sat < 0.16)
    orange = (r > g) & (g > b) & (r - b > 55) & (sat > 0.35)
    grey = (sat < 0.12) & (maximum > 70) & (maximum < 195)
    green = (g - np.maximum(r, b) > 18)
    blue = (b - np.maximum(r, g) > 18)

    shares = {name: float(mask.sum()) / total for name, mask in (
        ("cream", cream), ("orange", orange), ("grey", grey),
        ("green", green), ("blue", blue))}

    # The character's own signature: plenty of cream, some orange AND some grey.
    # Requiring both patches together is what keeps a white cat with no markings
    # and an orange tabby out.
    signature = min(shares["orange"], shares["grey"]) if shares["orange"] and shares["grey"] else 0.0
    score = (shares["cream"] * 2.0
             + min(shares["orange"], 0.35) * 2.0
             + min(shares["grey"], 0.35) * 2.0
             + min(signature, 0.12) * 6.0
             - shares["green"] * 2.5
             - shares["blue"] * 2.5)

    return {
        "file": path.name,
        "size": (width, height),
        "megapixels": round(width * height / 1e6, 2),
        "shares": {k: round(v, 4) for k, v in shares.items()},
        "score": round(float(score), 4),
    }


def build_sheets(entries: list[dict], cols: int, cell: int = 150,
                 per_sheet: int = 48, source: Path | None = None) -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    source = source or source_dir()
    sheets: list[Path] = []
    for start in range(0, len(entries), per_sheet):
        chunk = entries[start:start + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        label = 20
        sheet = Image.new("RGB", (cell * cols, (cell + label) * rows), (22, 22, 26))
        draw = ImageDraw.Draw(sheet)
        for index, entry in enumerate(chunk):
            path = source / entry["file"]
            try:
                sprite = Image.open(path).convert("RGB")
            except Exception:  # noqa: BLE001
                continue
            sprite.thumbnail((cell, cell), Image.LANCZOS)
            x = (index % cols) * cell + (cell - sprite.width) // 2
            y = (index // cols) * (cell + label) + (cell - sprite.height) // 2
            sheet.paste(sprite, (x, y))
            draw.text(((index % cols) * cell + 4, (index // cols) * (cell + label) + cell + 4),
                      f"{entry['file']} {entry['score']:.2f}", fill=(200, 200, 208))
        out = OUT / f"sheet-{start // per_sheet + 1:02d}.png"
        sheet.save(out)
        sheets.append(out)
    return sheets


def main() -> None:
    argv = sys.argv[1:]
    cols = int(argv[argv.index("--cols") + 1]) if "--cols" in argv else 8
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 48

    source = source_dir()
    files = sorted(p for p in source.iterdir() if p.suffix.lower() in EXTS)
    print(f"scoring {len(files)} downloaded images from {source}")

    entries: list[dict] = []
    for path in files:
        record = classify(path)
        if record:
            entries.append(record)
    entries.sort(key=lambda e: -e["score"])

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "scores.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n{'file':14s} {'size':>12s} {'score':>7s}  cream orange  grey green   blue")
    for entry in entries[:min(top, 30)]:
        s = entry["shares"]
        print(f"{entry['file']:14s} {str(entry['size']):>12s} {entry['score']:>7.2f}  "
              f"{s['cream']:.3f}  {s['orange']:.3f}  {s['grey']:.3f} {s['green']:.3f}  {s['blue']:.3f}")

    sheets = build_sheets(entries[:top], cols, source=source)
    print(f"\n{len(sheets)} contact sheets in {OUT}")
    for sheet in sheets:
        print(f"  {sheet.name}")


if __name__ == "__main__":
    main()
