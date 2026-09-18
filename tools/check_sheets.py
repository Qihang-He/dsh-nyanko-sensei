#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Diagnose the pose sheets: are they structurally usable?

A sheet can fail in ways that are invisible at a glance but fatal to the frame
extractor:

* **not a 2x2 grid** — one subject drawn across the whole image, or a single
  character with three empty quadrants. split_sheet would cut it into four
  useless pieces.
* **a different background colour per sheet** — the matte measures one screen
  colour per image, so a sheet that is half red and half green keys badly.
* **empty quadrants** — a sheet where only two cells contain a character
  produces two real frames and two blanks.

Each of those is measurable, and measuring is cheaper than eyeballing seven
sheets. What cannot be measured here is whether the poses are *good* or whether
the character is *on model* — that stays a human judgement, and the sheets that
pass this check still need to be looked at.

Usage:
    python check_sheets.py            # every sheet in work/sheets
    python check_sheets.py angry hop
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SHEETS = ROOT / "work" / "sheets"


def analyse(path: Path) -> dict:
    image = Image.open(path).convert("RGB").resize((512, 512), Image.LANCZOS)
    # float32, not int16: a squared channel difference reaches 65025 and overflows
    # a signed 16-bit integer, which produced NaNs from the sqrt and made one
    # sheet's verdict meaningless.
    arr = np.asarray(image).astype(np.float32)

    # Background = the single most common colour in the frame. Every one of these
    # images is a flat-coloured render, so this is reliable and does not need the
    # colour to be known in advance.
    flat = arr.reshape(-1, 3)
    quantised = (flat // 16 * 16)
    colours, counts = np.unique(quantised, axis=0, return_counts=True)
    background = colours[counts.argmax()]
    background_share = float(counts.max()) / len(flat)

    dist = np.sqrt(((arr - background) ** 2).sum(axis=2))
    subject = dist > 90

    quadrants = [
        float(subject[:256, :256].mean()),
        float(subject[:256, 256:].mean()),
        float(subject[256:, :256].mean()),
        float(subject[256:, 256:].mean()),
    ]
    # A quadrant is "occupied" when the subject covers a plausible fraction of it.
    occupied = [1 if 0.05 <= q <= 0.75 else 0 for q in quadrants]

    # Is there a visible gutter, or is the subject one continuous drawing?
    gutter_v = float(subject[:, 248:264].mean())
    gutter_h = float(subject[248:264, :].mean())

    return {
        "size": Image.open(path).size,
        "background": tuple(int(v) for v in background),
        "background_share": round(background_share, 3),
        "quadrants": [round(q, 3) for q in quadrants],
        "occupied": sum(occupied),
        "gutter_v": round(gutter_v, 3),
        "gutter_h": round(gutter_h, 3),
    }


def main() -> None:
    want = [a for a in sys.argv[1:] if not a.startswith("--")]
    files = ([SHEETS / f"{a}.jpg" for a in want] + [SHEETS / f"{a}.png" for a in want]
             if want else sorted(p for p in SHEETS.iterdir()
                                 if p.suffix in (".jpg", ".png")))
    files = [p for p in files if p.exists()]
    if not files:
        raise SystemExit(f"no sheets in {SHEETS}")

    print(f"{'sheet':16s} {'bg':>16s} {'bg%':>5s} {'occupied':>9s} "
          f"{'gutters':>13s}  verdict")
    for path in files:
        info = analyse(path)
        gutters = f"{info['gutter_v']:.2f}/{info['gutter_h']:.2f}"
        problems = []
        if info["occupied"] < 4:
            problems.append(f"only {info['occupied']}/4 quadrants occupied")
        if max(info["gutter_v"], info["gutter_h"]) > 0.15:
            problems.append("no clean gutter between cells")
        if info["background_share"] < 0.25:
            problems.append("background not flat/dominant")
        verdict = "usable" if not problems else "; ".join(problems)
        print(f"{path.stem:16s} {str(info['background']):>16s} "
              f"{info['background_share']:>5.2f} {info['occupied']:>9d}/4 "
              f"{gutters:>13s}  {verdict}")

    print()
    print("Note: this checks structure only. Whether the poses are good and the")
    print("character is on model is a judgement — look at work/sheet-review/.")


if __name__ == "__main__":
    main()
