#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Extract the reference stills whose backgrounds are not a flat colour.

`extract_refs.py` handles the easy case: a flat background, sampled from the
border, flood-filled from the frame edge. The grass and wooden-interior stills
defeat that, and the reason is worth stating because it dictates the fix.

The obvious approach — threshold on distance from a sampled background colour —
fails on these, and not because the tolerance is wrong. On the grass stills the
character fills the frame, so there is no crop that removes the background, and
grass is a *textured gradient*: a single sampled colour is far from most of it,
while a tolerance wide enough to cover the gradient starts eating the character.
Raising the tolerance makes the character vanish; lowering it leaves a green
fringe everywhere. There is no value in between.

What actually separates subject from grass is **saturation**, not colour
distance. Grass is a narrow, highly saturated green; the character is white,
cream, orange and grey, all far less saturated, plus a dark outline. So the
discriminator is "saturated and green-dominant", and the matte is then cleaned
by keeping only large blobs — which removes grass blades that survive as
speckle without touching a genuinely detached paw.

Usage:
    python extract_hard.py [image ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from extract_refs import (  # noqa: E402
    OUT, REFS, content_box, drop_small_blobs, pad_square, refine_alpha,
)


def saturation(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """HSV saturation, green excess, and value, in 0..1 / 0..255 units."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    maximum = np.maximum(np.maximum(r, g), b)
    minimum = np.minimum(np.minimum(r, g), b)
    sat = np.where(maximum > 1e-6, (maximum - minimum) / np.maximum(maximum, 1e-6), 0.0)
    green_dominance = g - np.maximum(r, b)
    return sat, green_dominance, maximum


def drop_border_components(mask: np.ndarray, max_fraction: float = 0.06) -> np.ndarray:
    """Drop blobs of `mask` that touch the frame edge and are small.

    On a grass still, blades and leaf fragments survive any colour test as
    scattered bright specks, and they are never part of the character. A
    component that touches the border *and* covers only a small part of the
    frame is background; the same blob in the middle could be a paw, so interior
    blobs are left alone.
    """
    from collections import deque

    h, w = mask.shape
    seen = np.zeros((h, w), dtype=bool)
    keep = mask.copy()
    limit = max_fraction * h * w
    for sy in range(h):
        for sx in range(w):
            if not mask[sy, sx] or seen[sy, sx]:
                continue
            blob: list[tuple[int, int]] = []
            queue = deque([(sy, sx)])
            seen[sy, sx] = True
            touches = False
            while queue:
                y, x = queue.popleft()
                blob.append((y, x))
                if y in (0, h - 1) or x in (0, w - 1):
                    touches = True
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        queue.append((ny, nx))
            if touches and len(blob) <= limit:
                for y, x in blob:
                    keep[y, x] = False
    return keep


# Per-image tuning. `green` is the green excess (G - max(R,B), 0..255) a pixel
# must show to count as foliage. Green excess rather than saturation is the
# decisive test: grass and the character's orange patch have similar saturation,
# so a saturation threshold deletes the orange forehead patch — which is exactly
# what an earlier revision of this file did. Orange has G below max(R,B), so its
# green excess is negative and it survives.
TUNING: dict[str, dict] = {
    # Front-facing head-and-shoulders on bright grass. Carries the most likeness
    # information of the whole set: slit eyes, wavy mouth, both forehead
    # patches and the divider between them, collar and bell.
    "OIP-C (2)": {"green": 10.0, "keep_ratio": 0.28},
    # Lying on grass, side-lit. The best available rest/sleep pose.
    "下载 (1)": {"green": 12.0, "keep_ratio": 0.28},
    # Sitting at a low table holding a cup. The room is warm and low-saturation,
    # so the foliage rule cannot find it; this one uses a colour distance
    # against the sampled interior instead, and the furniture is masked by
    # position.
    "OIP-C (1)": {"green": 0.0, "keep_ratio": 0.12,
                  "colour": ((48, 40, 26), 70.0),
                  "mask": [(0.00, 0.62, 0.42, 1.00),   # the table and cup, lower left
                           (0.00, 0.00, 1.00, 0.06)]},  # the dark top edge
}


def ring_samples(rgb: np.ndarray, inset: float, count: int = 24) -> np.ndarray:
    """Background colours sampled around a ring, so a gradient is followed."""
    h, w, _ = rgb.shape
    margin = max(2, int(min(h, w) * inset))
    ys = np.linspace(margin, h - 1 - margin, count).astype(int)
    xs = np.linspace(margin, w - 1 - margin, count).astype(int)
    samples = [rgb[margin, x] for x in xs]
    samples += [rgb[h - 1 - margin, x] for x in xs]
    samples += [rgb[y, margin] for y in ys]
    samples += [rgb[y, w - 1 - margin] for y in ys]
    return np.stack(samples)


def background_by_ring(rgb: np.ndarray, inset: float, tolerance: float) -> np.ndarray:
    """A pixel is background when it is near ANY sampled ring colour."""
    samples = ring_samples(rgb, inset).astype(np.float32)
    flat = rgb.reshape(-1, 3).astype(np.float32)
    # Distance to every sample, then take the minimum per pixel. Chunked to keep
    # the intermediate array small on large images.
    nearest = np.full(flat.shape[0], np.inf, dtype=np.float32)
    chunk = 4096
    for start in range(0, len(samples), chunk):
        block = samples[start:start + chunk]
        d = np.sqrt(((flat[:, None, :] - block[None, :, :]) ** 2).sum(axis=2))
        nearest = np.minimum(nearest, d.min(axis=1))
    return (nearest < tolerance).reshape(rgb.shape[:2])


def apply_masks(subject: np.ndarray, masks: list[tuple[float, float, float, float]]) -> int:
    """Blank rectangular regions given as (left, top, right, bottom) fractions."""
    h, w = subject.shape
    for left, top, right, bottom in masks:
        subject[int(h * top):int(h * bottom), int(w * left):int(w * right)] = False
    return len(masks)


def process(path: Path, spec: dict) -> dict:
    image = Image.open(path).convert("RGB")
    # Upscale before matting: the fringe is a sub-pixel effect at source size and
    # the alpha ramp has more room to be smooth.
    scale = max(1, int(760 / max(image.size)))
    if scale > 1:
        image = image.resize((image.width * scale, image.height * scale), Image.LANCZOS)
    rgb = np.asarray(image)

    if "colour" in spec:
        (target, tolerance) = spec["colour"]
        distance = np.sqrt(((rgb.astype(np.float32) - np.array(target, dtype=np.float32)) ** 2)
                           .sum(axis=2))
        background = distance < tolerance
    else:
        # Foliage = green-dominant. Green excess rather than saturation is the
        # decisive test: grass and the character's orange patch have similar
        # saturation, so a saturation threshold deletes the orange forehead
        # patch. Orange has G below max(R,B), so its green excess is negative.
        _, green, _ = saturation(rgb)
        background = green > spec["green"]
        background = drop_border_components(background, max_fraction=0.06)

    subject, dropped = drop_small_blobs(~background, keep_ratio=spec["keep_ratio"])
    dropped += apply_masks(subject, spec.get("mask", []))
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
        if path is None:
            print(f"{name:22s} (not found in {REFS})")
            continue
        spec = TUNING.get(name)
        if spec is None:
            print(f"{name:22s} (no tuning entry)")
            continue
        r = process(path, spec)
        print(f"{r['image'][:22]:22s} {str(r['source']):>11s} {r['subject_ratio']:>8.3f} "
              f"{str(r['cut_size']):>11s} {r['blobs_dropped']:>5d}")
    print(f"\ncut-outs and magenta checks in {OUT}")


if __name__ == "__main__":
    main()
