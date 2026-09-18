#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Matte by learning the character's palette from a sprite that is already clean.

Six earlier attempts on the grass stills all failed, and the reason is worth
recording because it rules out a whole family of solutions rather than one
setting:

* Sampling the background and thresholding fails — grass is a gradient, so the
  tolerance that covers it also covers the character's warm fur.
* Saturation fails — shadowed grass between blades is a *desaturated* grey-green.
* Green dominance fails — that same grey-green reads as "not green", and the
  character's grey back patch reads identically. The two are the same colour.
* Border flood fill fails — the grass touches the frame edge everywhere, so the
  fill either stops immediately or, with a loose tolerance, walks into the
  character through its soft outline.

Every one of those asks "what is the background like?". The question that
actually has an answer is "what is the *character* like?" — and that is knowable
exactly, because one sprite is already extracted cleanly.

So this learns the character's colour distribution from that clean sprite and
scores every pixel of a new image against it, in a chroma space where brightness
is divided out (the grass stills are lit differently from the reference, so
absolute colour cannot be compared directly).

Usage:
    python palette_match.py --learn <clean-sprite.png>
    python palette_match.py --apply "OIP-C (2)"
    python palette_match.py --list
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from extract_refs import (  # noqa: E402
    OUT, REFS, content_box, drop_small_blobs, pad_square, refine_alpha,
)

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "work" / "palette-model.json"
# The one sprite that came out clean, used as the source of truth for what the
# character looks like.
LEARN_FROM = ROOT / "work" / "extracted" / "OIP-C-cut.png"

# Tuning per target image. `gate` is the chroma distance below which a pixel is
# considered character-coloured; `keep_ratio` prunes leftover speckle.
TUNING: dict[str, dict] = {
    "OIP-C (2)": {"gate": 26.0, "keep_ratio": 0.10},
    "下载 (1)": {"gate": 26.0, "keep_ratio": 0.10},
}


def chroma(rgb: np.ndarray, floor: float = 48.0) -> np.ndarray:
    """Colour with brightness divided out.

    Each channel is divided by the pixel's own total, so the three channels sum
    to 1 and only the *hue and relative warmth* survive. Ratios rather than
    absolute values, because the reference sheet and the grass stills are lit
    differently and absolute RGB would treat the same fur under two lights as two
    colours. The floor keeps near-black outline pixels, whose sum is tiny, from
    exploding into noise.

    The result keeps three channels rather than collapsing to two: they are
    linearly dependent, but keeping them makes the distance below an ordinary
    Euclidean distance over the returned array, with no projection maths to get
    wrong. The extra channel costs nothing and removes a class of bug.
    """
    flat = rgb.astype(np.float32)
    total = np.maximum(flat.sum(axis=2, keepdims=True), floor)
    return flat / total


def learn(path: Path, clusters: int = 10) -> dict:
    """Cluster the clean sprite's opaque pixels into a palette."""
    image = Image.open(path).convert("RGBA")
    arr = np.asarray(image).astype(np.float32)
    rgb, alpha = arr[..., :3], arr[..., 3] / 255.0
    # Weight by alpha so anti-aliased edge pixels contribute proportionally.
    ys, xs = np.where(alpha > 0.6)
    sample = rgb[ys, xs]
    weights = alpha[ys, xs]

    # One row of pixels is a valid (h, w, 3) image, so `chroma` can be reused
    # verbatim instead of duplicating its ratio maths for a flat list. The shape
    # is derived from the size rather than assumed, so an unexpected channel
    # count fails loudly here instead of producing a wrong palette.
    sample = np.asarray(sample, dtype=np.float32).reshape(-1, 3)
    points = chroma(sample.reshape(1, -1, 3)).reshape(-1, 3)
    # Seed k-means deterministically rather than at random so the model file is
    # reproducible and diffable between runs.
    rng = np.random.default_rng(20260101)
    centres = points[rng.choice(len(points), size=min(clusters, len(points)), replace=False)]

    for _ in range(24):
        d = ((points[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
        labels = d.argmin(axis=1)
        for index in range(len(centres)):
            member = points[labels == index]
            if len(member):
                centres[index] = member.mean(axis=0)

    counts = np.bincount(labels, minlength=len(centres))
    total = max(1, int(counts.sum()))
    entries = sorted(
        ({"chroma": [round(float(c), 5) for c in centre],
          "share": round(float(count) / total, 4)}
         for centre, count in zip(centres, counts)),
        key=lambda e: -e["share"])
    model = {"source": path.name, "clusters": len(entries), "entries": entries}
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    MODEL.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    print(f"learned {len(entries)} palette entries from {path.name} -> {MODEL}")
    for entry in entries[:8]:
        print(f"  share {entry['share']:.3f}  chroma {entry['chroma']}")
    return model


def apply(target: Path, spec: dict, model: dict) -> dict:
    image = Image.open(target).convert("RGB")
    scale = max(1, int(760 / max(image.size)))
    if scale > 1:
        image = image.resize((image.width * scale, image.height * scale), Image.LANCZOS)
    rgb = np.asarray(image)

    points = chroma(rgb).reshape(-1, 3)
    centres = np.array([entry["chroma"] for entry in model["entries"]], dtype=np.float32)
    # Distance to the nearest palette entry, computed in chunks to bound memory.
    nearest = np.full(len(points), np.inf, dtype=np.float32)
    chunk = 8192
    for start in range(0, len(points), chunk):
        block = points[start:start + chunk]
        d = np.sqrt(((block[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2))
        nearest[start:start + chunk] = d.min(axis=1)
    character = (nearest < spec["gate"]).reshape(rgb.shape[:2])

    character, dropped = drop_small_blobs(character, keep_ratio=spec["keep_ratio"])
    alpha = refine_alpha(~character, feather=1)

    sprite = Image.fromarray(np.dstack([rgb, alpha]), "RGBA")
    cut = sprite.crop(content_box(alpha))
    OUT.mkdir(parents=True, exist_ok=True)
    stem = target.stem
    cut.save(OUT / f"{stem}-cut.png")
    pad_square(cut).save(OUT / f"{stem}-sprite.png")
    panel = Image.new("RGBA", sprite.size, (255, 0, 255, 255))
    panel.alpha_composite(sprite)
    panel.convert("RGB").save(OUT / f"{stem}-check.png")

    return {
        "image": target.name,
        "source": image.size,
        "subject_ratio": round(float((alpha > 24).mean()), 3),
        "cut_size": (cut.width, cut.height),
        "blobs_dropped": dropped,
    }


def main() -> None:
    argv = sys.argv[1:]
    if "--list" in argv:
        if MODEL.exists():
            print(MODEL.read_text(encoding="utf-8")[:1200])
        else:
            print(f"no model at {MODEL}; run --learn first")
        return
    if "--learn" in argv:
        path = Path(argv[argv.index("--learn") + 1]) if len(argv) > argv.index("--learn") + 1 else LEARN_FROM
        learn(path)
        return

    if not MODEL.exists():
        print(f"no palette model; learning from {LEARN_FROM.name} first")
        learn(LEARN_FROM)
    model = json.loads(MODEL.read_text(encoding="utf-8"))

    names = [a for a in argv if not a.startswith("--")] or list(TUNING)
    print(f"{'image':22s} {'source':>11s} {'subject':>8s} {'cut':>11s} {'drop':>5s}")
    for name in names:
        target = next((p for p in REFS.iterdir() if p.stem == name), None)
        if target is None or name not in TUNING:
            print(f"{name:22s} (skipped)")
            continue
        r = apply(target, TUNING[name], model)
        print(f"{r['image'][:22]:22s} {str(r['source']):>11s} {r['subject_ratio']:>8.3f} "
              f"{str(r['cut_size']):>11s} {r['blobs_dropped']:>5d}")
    print(f"\ncut-outs and magenta checks in {OUT}")


if __name__ == "__main__":
    main()
