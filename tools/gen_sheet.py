#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Produce the character sheet from the reference art, and check it is on-model.

This is the highest-leverage call in the whole asset build, and it is cheap
(about CNY 0.20), so it is worth doing carefully:

* The reference image is the approved sprite, flattened onto white. Seedream
  accepts a transparent PNG, but a reference with an alpha channel composites
  unpredictably on the model side, and white is what the character art already
  sits on.
* The prompt is deliberately short. The model is being *shown* the character, so
  the prompt's job is to ask for what the reference cannot convey — a neutral
  standing pose on a chroma-key background at a consistent size — not to
  re-describe the markings. Long descriptions are how the earlier text-only
  attempts drifted.

The output is written to work/sheet/ and a magenta check image alongside it, so
the background is verifiable at a glance rather than assumed.

Usage:
    python gen_sheet.py                 # one front view
    python gen_sheet.py --views 3       # ask for three candidates in one call
    python gen_sheet.py --compare       # put the reference next to the result
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from PIL import Image  # noqa: E402
from platform import Budget, DEFAULT_IMAGE_MODEL, generate_image, image_size  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "work" / "extracted" / "OIP-C-cut.png"
OUT = ROOT / "work" / "sheet"

# What the reference cannot state on its own. Deliberately not a description of
# the character: the model can see it.
PROMPT = (
    "Using the reference image, draw the same cat character as a clean "
    "full-body sprite for a 2D animation: standing on all four legs, facing the "
    "viewer, neutral expression, whole body inside the frame with a margin, "
    "flat cel-shaded anime style with firm outlines, identical fur markings and "
    "identical collar with its gold bell, on a completely flat pure green "
    "chroma-key background (uniform #00FF00) with no shadow, no floor and no "
    "gradient."
)


def flatten_on_white(path: Path) -> bytes:
    """The reference sprite without transparency, so compositing is predictable."""
    import io

    image = Image.open(path).convert("RGBA")
    canvas = Image.new("RGBA", image.size, (255, 255, 255, 255))
    canvas.alpha_composite(image)
    buffer = io.BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def magenta_check(png: bytes, dest: Path) -> None:
    """Composite onto magenta so any surviving background is impossible to miss."""
    import io

    image = Image.open(io.BytesIO(png)).convert("RGBA")
    panel = Image.new("RGBA", image.size, (255, 0, 255, 255))
    panel.alpha_composite(image)
    panel.convert("RGB").save(dest)


def compare(result: Path, dest: Path, height: int = 420) -> None:
    """Reference on the left, result on the right, same height."""
    reference = Image.open(REFERENCE).convert("RGBA")
    produced = Image.open(result).convert("RGBA")

    def scaled(image: Image.Image) -> Image.Image:
        factor = height / image.height
        return image.resize((max(1, int(image.width * factor)), height), Image.LANCZOS)

    left, right = scaled(reference), scaled(produced)
    gap = 24
    sheet = Image.new("RGB", (left.width + right.width + gap * 3, height + gap * 2),
                      (24, 24, 28))
    for image, columns in ((left, gap), (right, gap * 2 + left.width)):
        panel = Image.new("RGBA", image.size, (255, 255, 255, 255))
        panel.alpha_composite(image)
        sheet.paste(panel.convert("RGB"), (columns, gap))
    sheet.save(dest)


def main() -> None:
    argv = sys.argv[1:]
    views = 1
    if "--views" in argv:
        views = int(argv[argv.index("--views") + 1])

    if not REFERENCE.exists():
        raise SystemExit(f"no reference sprite at {REFERENCE}")

    OUT.mkdir(parents=True, exist_ok=True)
    reference = flatten_on_white(REFERENCE)
    print(f"reference: {REFERENCE.name} ({len(reference) / 1024:.0f} KiB, flattened on white)")
    print(f"model:     {DEFAULT_IMAGE_MODEL}")
    print(f"size:      {image_size(1024, 1024)}")
    print(f"views:     {views}")

    budget = Budget(5.0, dry_run="--dry-run" in argv, label="sheet")
    images = generate_image(PROMPT, model=DEFAULT_IMAGE_MODEL,
                            references=[reference], size=image_size(1024, 1024),
                            images=views, budget=budget)
    if not images:
        print(budget.report())
        return

    written: list[Path] = []
    for index, data in enumerate(images):
        suffix = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
        path = OUT / f"front-{index:02d}{suffix}"
        path.write_bytes(data)
        magenta_check(data, OUT / f"front-{index:02d}-check.png")
        written.append(path)
        print(f"  {path.name}  {len(data) / 1024:.0f} KiB")

    if written:
        compare(written[0], OUT / "compare.png")
        print(f"\ncompare: {OUT / 'compare.png'}")
        print(f"checks:  {OUT}/front-*-check.png")
    print(budget.report())


if __name__ == "__main__":
    main()
