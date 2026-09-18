#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Produce the character sheet on a background that cannot contaminate the art.

The first attempt used a green chroma key because that is the conventional
choice, and it produced a sprite with a green outline. Measurement showed the
fringe is not a matte failure — the pixels are genuinely green (about RGB
96/144/48), i.e. the model let the screen colour bleed into the character's
outline. A chroma key cannot fix that: the pixel is mostly character, so the key
correctly keeps it.

The fix is to stop asking for a colour that the character contains. The cat's own
palette is cream, dark orange, charcoal grey and brown, so:

* **green** collides with nothing in the character, but the model reflects it into
  the outline anyway because it is the universal "key this out" cue;
* **blue** collides with nothing either and is far less likely to be reflected,
  because classic anime cel art has no blue in this character at all;
* **magenta** is the safest of all against *this* character, and is what the
  matte check images already use — if it appears in the artwork it is
  unmistakable, which also makes review easier.

So this generates on magenta and keys magenta out. The cost is that a magenta
key is less forgiving of compression noise than green; the matte check image
makes any failure obvious immediately.

Two references are supplied, because they carry different information and the
model uses both: the earlier full-body sprite (proportions, markings layout) and
the front-facing head still (face, eyes, muzzle, collar detail).

Usage:
    python gen_sheet2.py                 # magenta background
    python gen_sheet2.py --bg blue       # blue background instead
    python gen_sheet2.py --views 2
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from PIL import Image  # noqa: E402
from platform import Budget, DEFAULT_IMAGE_MODEL, generate_image, image_size  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "work" / "sheet2"

# References, in the order the model will read them as "the character".
REFS = [
    ROOT / "work" / "extracted" / "OIP-C-cut.png",      # full body, clean matte
    ROOT / "work" / "extracted" / "OIP-C (2)-cut.png",  # front-facing head
]

BACKGROUNDS = {
    "magenta": ("pure flat magenta (#FF00FF)", "magenta"),
    "blue": ("pure flat bright blue (#0000FF)", "blue"),
    "green": ("completely flat pure green (#00FF00)", "green"),
}

# Short on purpose: the model is being shown the character, so the prompt asks
# only for what the references cannot convey — a clean neutral standing pose at a
# consistent scale — plus the background.
PROMPT = (
    "The reference images show the same cat character. Draw that exact character "
    "as a clean, high-resolution, front-facing full-body sprite for a 2D game: "
    "standing upright on all four legs, body fully inside the frame with a "
    "margin, neutral relaxed expression, flat cel-shaded Japanese anime style "
    "with firm clean outlines and no texture, preserving the fur markings "
    "exactly as shown (orange and dark grey patches on the forehead separated by "
    "a thin white stripe, mostly cream body, dark collar with a small gold bell, "
    "short tail). Draw it on a {background} with no shadow, no floor, no "
    "gradient and no reflection of the background colour onto the character. "
    "Keep the outline a clean dark brown-black — it must NOT be tinted {hue}."
)


def flatten_on_white(path: Path) -> bytes:
    image = Image.open(path).convert("RGBA")
    canvas = Image.new("RGBA", image.size, (255, 255, 255, 255))
    canvas.alpha_composite(image)
    buffer = io.BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def review(png: bytes, dest: Path) -> None:
    """Composite on magenta and on grey, so both a surviving background and a
    tinted outline are visible."""
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    for name, colour in (("magenta", (255, 0, 255, 255)), ("grey", (128, 128, 132, 255))):
        panel = Image.new("RGBA", image.size, colour)
        panel.alpha_composite(image)
        panel.convert("RGB").save(dest.with_name(f"{dest.stem}-{name}.png"))


def main() -> None:
    argv = sys.argv[1:]
    bg_key = "magenta"
    if "--bg" in argv:
        bg_key = argv[argv.index("--bg") + 1]
    if bg_key not in BACKGROUNDS:
        raise SystemExit(f"unknown background {bg_key!r}; pick from {list(BACKGROUNDS)}")
    background, hue = BACKGROUNDS[bg_key]

    views = int(argv[argv.index("--views") + 1]) if "--views" in argv else 1

    refs = [flatten_on_white(p) for p in REFS if p.exists()]
    if not refs:
        raise SystemExit(f"no reference images found among {[str(p) for p in REFS]}")
    print(f"references: {len(refs)} ({', '.join(p.name for p in REFS if p.exists())})")
    print(f"background: {background}")
    print(f"model:      {DEFAULT_IMAGE_MODEL}   views: {views}")

    OUT.mkdir(parents=True, exist_ok=True)
    budget = Budget(5.0, dry_run="--dry-run" in argv, label="sheet2")
    images = generate_image(PROMPT.format(background=background, hue=hue),
                            model=DEFAULT_IMAGE_MODEL, references=refs,
                            size=image_size(1024, 1024), images=views, budget=budget)
    if not images:
        print(budget.report())
        return

    for index, data in enumerate(images):
        suffix = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
        path = OUT / f"{bg_key}-{index:02d}{suffix}"
        path.write_bytes(data)
        review(data, OUT / f"{bg_key}-{index:02d}")
        print(f"  {path.name}  {len(data) / 1024:.0f} KiB")
    print(budget.report())


if __name__ == "__main__":
    main()
