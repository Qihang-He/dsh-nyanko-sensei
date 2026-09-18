#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate the character from a written specification alone.

No reference image. That is the decision this file encodes, and the reasoning is
worth recording because it reverses an earlier one:

* A reference image sets the *ceiling* on quality. The best reference available
  was a 180x240 crop of a compressed screenshot, and every artefact in the first
  Seedream output traced back to it — a fuzzy outline, drifted proportions.
* A reference also drags the background into the artwork. Asking for a green
  screen produced a green-tinted outline, because the model bled the screen
  colour into the character. That is unfixable by keying, since the pixel is
  mostly character.
* A written specification has no such ceiling, and for this character it is
  unusually effective: the design is simple, high-contrast and highly redundant,
  and the distinguishing features are few and describable — which is exactly the
  case where text beats a poor image.

The specification below is not invented. It was calibrated feature by feature
against the available stills, and the calibration record is in
tools/CALIBRATION.md. The single most important line is the forehead: it is
**three** bands — wide orange, thin white divider, wide dark grey — and without
that white divider the head reads as a generic calico.

Background is magenta, not green: the character contains no magenta at all, so a
spill would be unmistakable rather than blending into the artwork, and the matte
check composites on magenta for the same reason.

Usage:
    python gen_char.py                    # front view on magenta
    python gen_char.py --bg white         # on white, for a design sheet
    python gen_char.py --views 3
    python gen_char.py --pose "sitting"   # a different pose, same character
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from PIL import Image  # noqa: E402
from platform import Budget, DEFAULT_IMAGE_MODEL, generate_image, image_size  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "work" / "char"

# ---------------------------------------------------------------------------
# The character. Feature by feature, in the order they matter for likeness.
# ---------------------------------------------------------------------------
CHARACTER = (
    "a plump calico cat character from a Japanese anime series, drawn in clean "
    "flat cel-shaded 2D animation style with a firm dark-brown-black outline and "
    "no texture, no shading gradient and no realism. "
    # Silhouette. Stated first and in the negative because it is the thing most
    # easily got wrong: this cat is an egg, not a ball.
    "BODY: an egg — narrow at the shoulders, widest at the hips and low belly, a "
    "big round rump, and four short but clearly visible legs with white paws. "
    "Overweight and round, but never a perfect sphere and never a ball with no "
    "legs. A short stubby tail, barely more than a bump. "
    # Head.
    "HEAD: wide and rather flat, broader than tall, sitting directly on the body "
    "with no visible neck. Ears are large, tall, pointed triangles angled "
    "slightly outward. A small white rounded muzzle with a tiny pink-brown "
    "triangular nose and a thin curved mouth line. "
    # The eyes. The first attempt drew big round golden irises, which is wrong:
    # this character is almost always drawn with narrow slits.
    "EYES: narrow, thin, curved slit-like eyes that read as half-closed or closed "
    "in a sly smile, with small dark pupils; never large round cartoon eyes with "
    "big visible irises. The expression is sly, smug and mildly unimpressed. "
    # The signature marking. THREE bands, and the white divider is the point.
    #
    # The first text-only attempt is why this is worded the way it is: asked for
    # three bands "across the forehead", the model drew one thick white stripe
    # straight down the middle of the whole face. The divider is a NARROW gap
    # between two patches and only on the forehead — the muzzle and the area
    # below the eyes are white anyway, so the stripe must stop at eye level.
    "FUR: the body is mostly CREAM-WHITE. On the top of the head there are two "
    "large patches, one ORANGE and one DARK CHARCOAL GREY, side by side and "
    "separated by only a NARROW WHITE GAP of a few millimetres' width, running "
    "from between the ears down to just above the eyes and no further. The orange "
    "patch covers the left half of the crown as the viewer sees it and comes down "
    "around the left eye; the grey patch covers the right half of the crown and "
    "continues down over the right ear and the right side of the face. Below eye "
    "level the whole face and muzzle is plain cream-white with no white stripe "
    "and no patch. On the body, an ORANGE patch covers the left shoulder and left "
    "flank, and a DARK GREY patch covers the right flank and rump; the chest, the "
    "belly and all four paws are plain cream-white. "
    # Accessory. The first attempt omitted it entirely.
    "ACCESSORY: a thin dark-brown collar around the neck with a small round GOLD "
    "BELL hanging at the front centre. "
    # Whiskers, which the model over-promises by default.
    "WHISKERS: only three very short, thin, subtle whisker strands per side, "
    "barely longer than the muzzle — not long prominent whiskers. "
    # Expression marks, which the character shows when pleased or embarrassed.
    "Three short red-orange diagonal strokes on each cheek. "
    # The traps. Named explicitly because the model reaches for them by default.
    "Do NOT draw tabby stripes anywhere on the head, body, legs or tail. Do NOT "
    "ring or band the tail — the tail is a single short stubby shape in one "
    "colour. Do NOT give it long thin legs, a pointed snout, a long neck, a "
    "fluffy coat, or human-like hands. Do NOT add a long white stripe down the "
    "centre of the face."
)

BACKGROUNDS = {
    "magenta": "on a completely flat uniform magenta background (#FF00FF) that "
               "fills the whole frame, with absolutely no shadow, no cast shadow "
               "on the ground, no floor, no reflection, no mirrored copy of the "
               "character and no magenta bounced onto the character",
    "white": "on a plain pure white background with no shadow, no reflection and "
             "no floor",
    "green": "on a completely flat uniform green background (#00FF00) with no "
             "shadow, no reflection, no floor and no green bounced onto the "
             "character",
    "blue": "on a completely flat uniform blue background (#0000FF) with no "
            "shadow, no reflection, no floor and no blue bounced onto the "
            "character",
}

POSES = {
    "front": "Standing on all four legs with the body horizontal and the head "
             "facing the viewer — a standing quadruped pose, NOT sitting and NOT "
             "on its haunches. Whole body inside the frame with a clear margin on "
             "all four sides.",
    "sitting": "Sitting upright on its haunches with the front paws together in "
               "front, facing the viewer, eyes half-closed in a contented smile.",
    "sleeping": "Curled up asleep on the ground, eyes closed, tail tucked, body a "
                "compact rounded shape.",
    "side": "Full side profile, standing on all four legs facing to the right, "
            "head level.",
}


def review(png: bytes, dest: Path) -> None:
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    for name, colour in (("magenta", (255, 0, 255, 255)),
                         ("grey", (128, 128, 132, 255))):
        panel = Image.new("RGBA", image.size, colour)
        panel.alpha_composite(image)
        panel.convert("RGB").save(dest.with_name(f"{dest.stem}-{name}.png"))


def main() -> None:
    argv = sys.argv[1:]
    bg = argv[argv.index("--bg") + 1] if "--bg" in argv else "magenta"
    pose = argv[argv.index("--pose") + 1] if "--pose" in argv else "front"
    views = int(argv[argv.index("--views") + 1]) if "--views" in argv else 1
    if bg not in BACKGROUNDS:
        raise SystemExit(f"unknown background {bg!r}; pick from {list(BACKGROUNDS)}")
    if pose not in POSES:
        raise SystemExit(f"unknown pose {pose!r}; pick from {list(POSES)}")

    prompt = (f"Draw {CHARACTER} {POSES[pose]} Square 1:1 composition, the "
              f"character centred and at a consistent scale, {BACKGROUNDS[bg]}.")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{pose}-{bg}.prompt.txt").write_text(prompt, encoding="utf-8")
    print(f"prompt: {len(prompt)} chars -> {OUT / f'{pose}-{bg}.prompt.txt'}")
    print(f"model:  {DEFAULT_IMAGE_MODEL}   pose: {pose}   background: {bg}   views: {views}")

    budget = Budget(5.0, dry_run="--dry-run" in argv, label=f"char {pose}")
    images = generate_image(prompt, model=DEFAULT_IMAGE_MODEL,
                            size=image_size(1024, 1024), images=views, budget=budget)
    if not images:
        print(budget.report())
        return

    for index, data in enumerate(images):
        suffix = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
        path = OUT / f"{pose}-{bg}-{index:02d}{suffix}"
        path.write_bytes(data)
        review(data, OUT / f"{pose}-{bg}-{index:02d}")
        print(f"  {path.name}  {len(data) / 1024:.0f} KiB")
    print(budget.report())


if __name__ == "__main__":
    main()
