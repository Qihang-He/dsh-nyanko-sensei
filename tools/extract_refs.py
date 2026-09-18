#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Can the character be lifted cleanly out of the reference stills?

This decides the whole fallback plan. If the cat can be extracted from the
supplied reference art, the pet's animations can be built by transforming *that
art* — 100% likeness, no image-generation credential needed, no network. If it
cannot, the fallback is dead and a generation key is unavoidable.

So: rather than assume, measure. For every reference image this samples the
background colour from the border, builds a matte with connected-component
cleanup, reports how much of the frame survived, and writes a visual check on a
magenta panel where any leftover background is impossible to miss.

Usage:
    python extract_refs.py            # extract + report + write checks
    python extract_refs.py --view     # also print a per-image swatch summary
"""
from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "work" / "ref"
OUT = ROOT / "work" / "extracted"


def background_colour(rgb: np.ndarray, inset: float = 0.06) -> np.ndarray:
    """Median colour of a border band, sampling *inside* the frame.

    Sampling the outermost rows would pick up the letterboxing and the caption
    strips some of these stills carry, so the band starts `inset` in and skips
    the very edge.
    """
    h, w, _ = rgb.shape
    band = max(2, int(min(h, w) * 0.06))
    off = max(1, int(min(h, w) * inset))
    top = rgb[off:off + band].reshape(-1, 3)
    bottom = rgb[h - off - band:h - off].reshape(-1, 3)
    left = rgb[:, off:off + band].reshape(-1, 3)
    right = rgb[:, w - off - band:w - off].reshape(-1, 3)
    return np.median(np.concatenate([top, bottom, left, right]), axis=0)


def background_mask(rgb: np.ndarray, tolerance: float = 42.0) -> np.ndarray:
    """Pixels close to the sampled background colour, in RGB distance."""
    background = background_colour(rgb)
    distance = np.sqrt(((rgb.astype(np.float32) - background) ** 2).sum(axis=2))
    return distance < tolerance


def drop_small_blobs(mask: np.ndarray, keep_ratio: float = 0.04) -> tuple[np.ndarray, int]:
    """Remove connected blobs far smaller than the largest one.

    The subject is one big blob plus, at most, a few genuinely separated pieces
    (a detached paw, a tail tip). Anything an order of magnitude smaller than the
    body is not part of the character — Japanese onomatopoeia captions and stray
    background specks live there. Returns the cleaned mask and how many blobs
    were dropped, so the caller can report it rather than silently alter art.
    """
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    sizes: list[int] = [0]
    current = 0
    for start_y in range(h):
        for start_x in range(w):
            if not mask[start_y, start_x] or labels[start_y, start_x]:
                continue
            current += 1
            size = 0
            queue = deque([(start_y, start_x)])
            labels[start_y, start_x] = current
            while queue:
                y, x = queue.popleft()
                size += 1
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not labels[ny, nx]:
                        labels[ny, nx] = current
                        queue.append((ny, nx))
            sizes.append(size)

    if current == 0:
        return mask, 0
    biggest = max(sizes[1:])
    floor = biggest * keep_ratio
    keep = {index for index, size in enumerate(sizes) if size >= floor}
    dropped = sum(1 for i in range(1, current + 1) if i not in keep)
    return np.isin(labels, list(keep)), dropped


def pad_square(sprite: Image.Image, margin: float = 0.06) -> Image.Image:
    """Place the cut-out on a square canvas with a margin, bottom-anchored.

    Pet frames are scaled by height and anchored on a ground line, so a square
    canvas with the character resting low in it keeps a walking sprite and a
    sitting sprite on the same floor without per-frame maths later.
    """
    w, h = sprite.size
    side = int(max(w, h) * (1 + margin * 2))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(sprite, ((side - w) // 2, side - h - int(side * margin * 0.5)))
    return canvas


def flood_from_border(background: np.ndarray) -> np.ndarray:
    """Background connected to the frame edge.

    A plain colour threshold also punches holes wherever the character happens to
    match the background — a white cat on a white-ish panel would lose its chest.
    Only background *reachable from the border* is really background, so this
    flood-fills from the edge and discards interior matches.
    """
    h, w = background.shape
    reachable = np.zeros_like(background, dtype=bool)
    queue: deque[tuple[int, int]] = deque()

    for x in range(w):
        for y in (0, h - 1):
            if background[y, x] and not reachable[y, x]:
                reachable[y, x] = True
                queue.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if background[y, x] and not reachable[y, x]:
                reachable[y, x] = True
                queue.append((y, x))

    while queue:
        y, x = queue.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and background[ny, nx] and not reachable[ny, nx]:
                reachable[ny, nx] = True
                queue.append((ny, nx))
    return reachable


def refine_alpha(mask: np.ndarray, feather: int = 1) -> np.ndarray:
    """Turn a boolean background mask into a soft alpha channel.

    The source art is heavily JPEG-compressed, so a hard cut leaves a jagged
    halo. A small box blur on the matte gives an antialiased edge that survives
    being scaled down to pet size.
    """
    alpha = (~mask).astype(np.float32)
    if feather > 0:
        k = feather * 2 + 1
        padded = np.pad(alpha, feather, mode="edge")
        summed = np.zeros_like(alpha)
        for dy in range(k):
            for dx in range(k):
                summed += padded[dy:dy + alpha.shape[0], dx:dx + alpha.shape[1]]
        alpha = summed / (k * k)
    return np.clip(alpha * 255.0, 0, 255).astype(np.uint8)


def content_box(alpha: np.ndarray, threshold: int = 24) -> tuple[int, int, int, int]:
    ys, xs = np.where(alpha > threshold)
    if len(xs) == 0:
        return 0, 0, alpha.shape[1], alpha.shape[0]
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def swatches(rgb: np.ndarray, mask: np.ndarray, top: int = 5) -> list[tuple[int, tuple[int, int, int]]]:
    """Dominant colours inside the subject, quantised — a crude likeness check."""
    subject = rgb[~mask].reshape(-1, 3)
    if subject.size == 0:
        return []
    quantised = (subject // 24 * 24)
    colours, counts = np.unique(quantised, axis=0, return_counts=True)
    order = np.argsort(-counts)[:top]
    return [(int(counts[i]), tuple(int(v) for v in colours[i])) for i in order]


# Some stills carry an onomatopoeia caption ("ぬぁ〜") baked into a corner. It is
# foreground by colour, so no threshold can separate it: it has to be cleared by
# position. The value is the square fraction of the image width to blank in the
# TOP-RIGHT corner, measured by eye off the -check.png output. Listed only where
# a caption actually exists, so nothing is blanked on the others.
TEXT_ZONES: dict[str, float] = {
    "OIP-C": 0.34,
}


def process(path: Path, verbose: bool) -> dict:
    return _process(path, verbose, TEXT_ZONES.get(path.stem, 0.0))


def _process(path: Path, verbose: bool, text_zone: float) -> dict:
    image = Image.open(path).convert("RGB")
    rgb = np.asarray(image)
    background = background_mask(rgb)
    edge_background = flood_from_border(background)

    # Subject = everything the flood fill could not reach from the frame edge.
    subject = ~edge_background
    subject, dropped = drop_small_blobs(subject, keep_ratio=0.04)

    # Some stills carry a caption (onomatopoeia) in a corner. It is foreground by
    # colour, so no threshold can separate it and it must be masked by position;
    # `text_zone` is the square fraction of the width to clear in the top-right.
    if text_zone > 0:
        h, w = subject.shape
        zone = int(w * text_zone)
        subject[:zone, w - zone:] = False
        dropped += 1

    alpha = refine_alpha(~subject, feather=1)

    rgba = np.dstack([rgb, alpha])
    sprite = Image.fromarray(rgba, "RGBA")
    box = content_box(alpha)

    OUT.mkdir(parents=True, exist_ok=True)
    stem = path.stem
    cut = sprite.crop(box)
    cut.save(OUT / f"{stem}-cut.png")
    pad_square(cut).save(OUT / f"{stem}-sprite.png")

    # Visual check on a colour the source art never uses, so leftover background
    # or a hole punched through the character is immediately obvious.
    panel = Image.new("RGBA", sprite.size, (255, 0, 255, 255))
    panel.alpha_composite(sprite)
    panel.convert("RGB").save(OUT / f"{stem}-check.png")

    subject_ratio = float((alpha > 24).mean())
    holes = int((alpha <= 24).sum() - edge_background.sum())
    report = {
        "image": path.name,
        "size": image.size,
        "subject_ratio": round(subject_ratio, 3),
        "cut_size": (cut.width, cut.height),
        "interior_holes_px": max(0, holes),
        "blobs_dropped": dropped,
        "background_rgb": tuple(int(v) for v in background_colour(rgb)),
    }
    if verbose:
        report["top_colours"] = swatches(rgb, edge_background)
    return report


def build_contact_sheet() -> Path | None:
    """One image showing every extracted sprite on a magenta panel.

    Reviewing five separate checks is tedious, and the point of this stage is a
    single judgement — "can this art be animated?" — so the sheets are combined
    with the filename under each one.
    """
    sprites = sorted(OUT.glob("*-sprite.png"))
    if not sprites:
        return None
    cell = 220
    cols = min(len(sprites), 5)
    rows = (len(sprites) + cols - 1) // cols
    label = 22
    sheet = Image.new("RGB", (cell * cols, (cell + label) * rows), (255, 0, 255))
    for index, path in enumerate(sprites):
        sprite = Image.open(path).convert("RGBA")
        scale = min(cell / sprite.width, cell / sprite.height)
        sprite = sprite.resize((max(1, int(sprite.width * scale)),
                                max(1, int(sprite.height * scale))), Image.LANCZOS)
        x = (index % cols) * cell + (cell - sprite.width) // 2
        y = (index // cols) * (cell + label) + (cell - sprite.height)
        sheet.paste(sprite, (x, y), sprite)
    out = OUT / "contact-sheet.png"
    sheet.save(out)
    return out


def main() -> None:
    verbose = "--view" in sys.argv
    if not REFS.is_dir():
        raise SystemExit(f"no reference directory at {REFS}")
    images = sorted(p for p in REFS.iterdir()
                    if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp"))
    if not images:
        raise SystemExit(f"no images in {REFS}")

    print(f"{'image':22s} {'size':>11s} {'subject':>8s} {'cut':>11s} "
          f"{'holes':>6s} {'drop':>5s}  bg")
    for path in images:
        r = process(path, verbose)
        print(f"{r['image'][:22]:22s} {str(r['size']):>11s} {r['subject_ratio']:>8.3f} "
              f"{str(r['cut_size']):>11s} {r['interior_holes_px']:>6d} "
              f"{r['blobs_dropped']:>5d}  {r['background_rgb']}")
        if verbose and r.get("top_colours"):
            for count, colour in r["top_colours"]:
                print(f"    {count:>7d} px  rgb{colour}")

    sheet = build_contact_sheet()
    print(f"\ncut-outs, magenta checks and sprite canvases in {OUT}")
    if sheet:
        print(f"contact sheet: {sheet}")


if __name__ == "__main__":
    main()
