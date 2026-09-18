#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Adopt a generated image as the pet's base sprite.

Choosing which generation to keep is a human judgement, so this does not score
candidates — it takes the one it is told to take, mats it, and reports whether the
result is usable. The report is the useful part: a sprite is only usable if the
matte is clean and the character fills enough of the frame to survive being scaled
down to pet size.

The tint budget matters here. A generated image on a saturated background often
carries a little of that colour on the character's outline, and this project was
bitten once already by a green screen bleeding into the artwork. Despill runs
before the report so the measured tint is the post-fix value.

Usage:
    python adopt.py work/clean/clean-00.jpg
    python adopt.py work/clean/clean-00.jpg --name base2
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import build_assets as B  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPRITES = ROOT / "work" / "sprites"


def report(path: Path, keyed: Image.Image) -> dict:
    arr = np.asarray(keyed)
    rgb = arr[..., :3].astype(np.float32)
    alpha = arr[..., 3]
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    excess = {
        "green": float((g - np.maximum(r, b))[alpha > 200].max()) if (alpha > 200).any() else 0.0,
        "magenta": float((np.minimum(r, b) - g)[alpha > 200].max()) if (alpha > 200).any() else 0.0,
    }
    box = B.content_box(keyed)
    return {
        "size": keyed.size,
        "transparent_pct": round(100 * float((alpha < 16).mean()), 1),
        "character_box": box,
        "character_px": (box[2] - box[0], box[3] - box[1]),
        "fills_frame_pct": round(100 * float(((alpha > 24).sum()) / (keyed.width * keyed.height)), 1),
        "outline_tint": {k: round(v, 1) for k, v in excess.items()},
    }


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        raise SystemExit("usage: python adopt.py <image> [--name base]")
    source = Path(argv[0])
    if not source.is_absolute():
        source = (ROOT / source).resolve()
    if not source.exists():
        raise SystemExit(f"no such image: {source}")
    name = argv[argv.index("--name") + 1] if "--name" in argv else "base"

    image = Image.open(source).convert("RGB")
    keyed = B.chroma_to_alpha(image)
    info = report(source, keyed)

    SPRITES.mkdir(parents=True, exist_ok=True)
    cut = keyed.crop(info["character_box"])
    target = SPRITES / f"{name}.png"

    # Keep a copy of the previous sprite whenever the name is reused: the choice
    # of base is a judgement call, and re-running this should not be destructive.
    if target.exists():
        backup = SPRITES / f"{name}-previous.png"
        shutil.copy2(target, backup)
        print(f"previous sprite kept at {backup.name}")

    cut.save(target)
    panel = Image.new("RGBA", keyed.size, (255, 0, 255, 255))
    panel.alpha_composite(keyed)
    panel.convert("RGB").save(SPRITES / f"{name}-check.png")

    print(f"source:      {source.relative_to(ROOT)}  {image.size[0]}x{image.size[1]}")
    print(f"sprite:      {target.relative_to(ROOT)}  {cut.size[0]}x{cut.size[1]}")
    print(f"transparent: {info['transparent_pct']}% of the frame")
    print(f"character:   {info['character_px'][0]}x{info['character_px'][1]} px, "
          f"{info['fills_frame_pct']}% of the frame")
    print(f"outline tint: {info['outline_tint']}  (green/magenta excess on opaque px; "
          f"lower is cleaner)")
    print(f"check image: {SPRITES.relative_to(ROOT)}/{name}-check.png")
    print()
    if info["character_px"][1] < 400:
        print("WARNING: the character is short; detail will be lost at pet size.")
    if max(info["outline_tint"].values()) > 40:
        print("WARNING: notable background tint on the outline.")


if __name__ == "__main__":
    main()
