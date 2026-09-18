#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Border-connected matting, for backgrounds that are a textured gradient.

Both earlier attempts at the grass stills failed, and the reasons are worth
keeping because they are the reason this approach exists:

1. **Distance from a sampled colour** — grass is a gradient, so a tolerance wide
   enough to cover it also covers the character's warm fur. There is no working
   value.
2. **Green dominance** — the shadowed grass between blades is a *desaturated*
   grey-green, which reads as "not green" and survives as foreground, while the
   character's grey back patch reads the same way and gets deleted.

The property that actually holds is connectivity, not colour: the background is
whatever you can reach from the frame edge without crossing a line. The
character is drawn with a firm dark outline, and that outline is a closed curve,
so a flood fill started at the border stops at it. Whatever the fill could not
reach is the character, whatever colour any individual pixel happens to be.

This is why the outline matters for more than looks, and why the fill's
tolerance can stay generous: it only has to be tight enough not to jump the
outline, not tight enough to model the grass.

Usage:
    python extract_border.py [image ...]
"""
from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from extract_refs import (  # noqa: E402
    OUT, REFS, content_box, drop_small_blobs, pad_square, refine_alpha,
)


def flood_background(rgb: np.ndarray, tolerance: float) -> np.ndarray:
    """Background reachable from the frame edge, hopping between similar pixels.

    Two conditions gate every hop, and both are needed:

    * the *step* from the pixel the fill spread from must be small, so the fill
      can follow a grass gradient whose far corner is a different shade;
    * the *pixel itself* must be close to the sampled background colour, so the
      fill cannot creep across a soft or anti-aliased outline one small step at a
      time.

    Step-only leaking is the failure mode that matters here: an anime still has a
    soft, one-pixel outline in places, and a step test alone walks straight
    through it, flooding the whole character from the inside. That is exactly
    what an earlier revision did, and why the subject ratio collapsed to 3%.
    """
    h, w, _ = rgb.shape
    flat = rgb.astype(np.float32)

    band = max(2, int(min(h, w) * 0.05))
    border = np.concatenate([
        flat[:band].reshape(-1, 3), flat[-band:].reshape(-1, 3),
        flat[:, :band].reshape(-1, 3), flat[:, -band:].reshape(-1, 3),
    ])
    reference = np.median(border, axis=0)
    distance = np.sqrt(((flat - reference) ** 2).sum(axis=2))
    near_background = distance < tolerance * 1.7

    background = np.zeros((h, w), dtype=bool)
    queue: deque[tuple[int, int]] = deque()

    def push(y: int, x: int) -> None:
        if near_background[y, x] and not background[y, x]:
            background[y, x] = True
            queue.append((y, x))

    for x in range(w):
        push(0, x)
        push(h - 1, x)
    for y in range(h):
        push(y, 0)
        push(y, w - 1)

    while queue:
        y, x = queue.popleft()
        here = flat[y, x]
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not background[ny, nx]:
                if not near_background[ny, nx]:
                    continue
                if float(np.sqrt(((flat[ny, nx] - here) ** 2).sum())) < tolerance:
                    push(ny, nx)
    return background


# `tolerance` is the per-step colour change the fill will accept. It only has to
# be smaller than the jump across the character's outline.
TUNING: dict[str, dict] = {
    # Front-facing head-and-shoulders on bright grass.
    "OIP-C (2)": {"tolerance": 34.0, "keep_ratio": 0.05},
    # Lying on grass, side-lit, with a soft shadow along the lower edge.
    "下载 (1)": {"tolerance": 30.0, "keep_ratio": 0.05},
}


def process(path: Path, spec: dict) -> dict:
    image = Image.open(path).convert("RGB")
    scale = max(1, int(760 / max(image.size)))
    if scale > 1:
        image = image.resize((image.width * scale, image.height * scale), Image.LANCZOS)
    rgb = np.asarray(image)

    background = flood_background(rgb, spec["tolerance"])
    subject, dropped = drop_small_blobs(~background, keep_ratio=spec["keep_ratio"])
    alpha = refine_alpha(~subject, feather=1)

    sprite = Image.fromarray(np.dstack([rgb, alpha]), "RGBA")
    cut = sprite.crop(content_box(alpha))

    OUT.mkdir(parents=True, exist_ok=True)
    stem = path.stem
    cut.save(OUT / f"{stem}-cut.png")
    pad_square(cut).save(OUT / f"{stem}-sprite.png")
    panel = Image.new("RGBA", sprite.size, (255, 0, 255, 255))
    panel.alpha_composite(sprite)
    panel.convert("RGB").save(OUT / f"{stem}-check.png")

    return {
        "image": path.name,
        "source": image.size,
        "subject_ratio": round(float((alpha > 24).mean()), 3),
        "cut_size": (cut.width, cut.height),
        "blobs_dropped": dropped,
    }


def main() -> None:
    wanted = sys.argv[1:]
    names = wanted or list(TUNING)
    print(f"{'image':22s} {'source':>11s} {'subject':>8s} {'cut':>11s} {'drop':>5s}")
    for name in names:
        path = next((p for p in REFS.iterdir() if p.stem == name), None)
        if path is None or name not in TUNING:
            print(f"{name:22s} (skipped)")
            continue
        r = process(path, TUNING[name])
        print(f"{r['image'][:22]:22s} {str(r['source']):>11s} {r['subject_ratio']:>8.3f} "
              f"{str(r['cut_size']):>11s} {r['blobs_dropped']:>5d}")
    print(f"\ncut-outs and magenta checks in {OUT}")


if __name__ == "__main__":
    main()
