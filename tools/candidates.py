#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Render the same character description with several image models.

Picking the art style is the one decision that is worth doing by eye, so this
script produces a side-by-side shortlist instead of guessing. Output lands in
``work/candidates/`` with the model id in the file name.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gen_art  # noqa: E402
from ofox import generate_image  # noqa: E402

MODELS = [
    "google/gemini-3.1-flash-image",
    "google/gemini-3.1-flash-lite-image",
    "google/gemini-3-pro-image",
    "google/gemini-2.5-flash-image",
    "microsoft/mai-image-2.5-pro",
    "openai/gpt-image-2",
]


def main() -> None:
    out_dir = gen_art.ROOT / "work" / "candidates"
    out_dir.mkdir(parents=True, exist_ok=True)
    pose = gen_art.SHEET_VIEWS["front"]
    prompt = gen_art.sheet_prompt([pose] * 4)
    (out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    only = sys.argv[1:]
    for model in MODELS:
        if only and not any(o in model for o in only):
            continue
        slug = model.replace("/", "__")
        out = out_dir / f"front-{slug}.png"
        if out.exists() and out.stat().st_size > 0:
            print(f"= {model} (cached)")
            continue
        print(f"> {model}", flush=True)
        try:
            generate_image(prompt, model=model, out=out, retries=2)
            print(f"  ok {out.stat().st_size / 1024:.0f} KiB")
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"  FAIL {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
