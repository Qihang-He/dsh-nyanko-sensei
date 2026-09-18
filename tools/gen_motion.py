#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Animate an existing illustration instead of generating new art.

Every generation route needs a credential, a balance, and a model that will
follow a 4000-character spec — and even then the likeness is an approximation.
This stage sidesteps all of it: the character art is taken as given and the
motion is produced by *deforming that art*.

That is why this exists as a separate path rather than a fallback hack. For a
desktop pet the win is large:

* **Likeness is exact.** The pixels are the original illustration at every frame,
  so there is nothing to drift.
* **No network, no key, no balance.** Rendering is pure local image maths.
* **Deterministic.** The same inputs always produce the same WebM, byte for byte
  bar encoder noise, so a build can be diffed.

The trade-off is honest and worth stating: motion is derived from a single
drawing, so limbs cannot articulate independently and expressions cannot change
beyond what deformation can fake. It is a puppet, not a redrawn animation.

How the deformation works
-------------------------
A displacement field is built per animation as a sum of *local* falloff
functions, then the whole frame is resampled once through that field. Building it
as one field matters: warping an image in successive passes resamples repeatedly
and visibly softens the art, whereas one pass keeps every source pixel used
exactly once.

Region shapes are ellipses in normalised (0..1) sprite coordinates, so an
animation is described in numbers that stay readable and portable between
sprites of different sizes.

Usage:
    python gen_motion.py                 # render every animation
    python gen_motion.py idle sleep      # render selected ones
    python gen_motion.py --sheet         # also write a review contact sheet
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SPRITE_DIR = ROOT / "work" / "sprites"
FRAMES = ROOT / "work" / "motion"
ASSETS = ROOT / "assets" / "anims"

# Final canvas. The source illustration is small, so frames are rendered at a
# higher internal size and downsampled once at the end: warping at the source
# resolution would destroy the linework, and shipping the upscaled size would
# waste bytes for no visible gain at pet scale.
RENDER = 720
CANVAS = (384, 384)
TARGET_H = 320
GROUND_Y = 366
FPS = 12
FFMPEG = "ffmpeg"


# ---------------------------------------------------------------------------
# the sprite
# ---------------------------------------------------------------------------
def load_sprite(name: str = "base") -> tuple[np.ndarray, np.ndarray]:
    """Load an RGBA sprite, trim to content, and return (rgb float, alpha float).

    Rendering happens in float and in premultiplied form: an unpremultiplied
    warp pulls colour out of fully transparent pixels into the silhouette edge,
    which shows up as a dark fringe once the frames are composited.
    """
    path = None
    for suffix in (".png", ".webp", ".jpg"):
        candidate = SPRITE_DIR / f"{name}{suffix}"
        if candidate.exists():
            path = candidate
            break
    if path is None:
        raise SystemExit(f"no sprite at {SPRITE_DIR / name}.* — run the extractor first")

    image = Image.open(path).convert("RGBA")
    arr = np.asarray(image).astype(np.float32) / 255.0
    rgb, alpha = arr[..., :3], arr[..., 3]

    ys, xs = np.where(alpha > 0.02)
    if len(xs) == 0:
        raise SystemExit(f"{path} is fully transparent")
    rgb = rgb[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    alpha = alpha[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

    # Scale so the character stands TARGET_H tall on a RENDER-wide stage.
    scale = (TARGET_H / CANVAS[1]) * RENDER / rgb.shape[0]
    new_size = (max(1, round(rgb.shape[1] * scale)), max(1, round(rgb.shape[0] * scale)))
    rgb = np.asarray(Image.fromarray((rgb * 255).astype(np.uint8))
                     .resize(new_size, Image.LANCZOS)).astype(np.float32) / 255.0
    alpha = np.asarray(Image.fromarray((alpha * 255).astype(np.uint8))
                       .resize(new_size, Image.LANCZOS)).astype(np.float32) / 255.0
    return rgb, alpha


# ---------------------------------------------------------------------------
# displacement field
# ---------------------------------------------------------------------------
def ellipse_weight(xx: np.ndarray, yy: np.ndarray, cx: float, cy: float,
                   rx: float, ry: float, power: float = 2.0) -> np.ndarray:
    """Smooth 1-at-centre → 0-at-rim falloff over an ellipse.

    `power` steepens the shoulder; 2.0 is a soft bell, higher values approach a
    flat-topped disc. Soft is the right default because a hard region boundary
    shows up as a crease across the artwork.
    """
    dx = (xx - cx) / max(1e-6, rx)
    dy = (yy - cy) / max(1e-6, ry)
    d = np.sqrt(dx * dx + dy * dy)
    return np.clip(1.0 - d, 0.0, 1.0) ** power


def warp(rgb: np.ndarray, alpha: np.ndarray, dx: np.ndarray, dy: np.ndarray,
         scale: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Resample the sprite through a displacement field in one pass.

    Inverse mapping: for every output pixel, sample the source at
    (x - dx, y - dy). Bilinear, with the sample clamped at the border so a
    displacement can never wrap around and drag the far edge of the sprite into
    the frame.
    """
    h, w = alpha.shape
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    sx = xs - dx
    sy = ys - dy

    if scale is not None:
        # Scale about the sprite's own centre, expressed as a source offset.
        cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
        factor = np.clip(scale, 0.2, 5.0)
        sx = cx + (sx - cx) / factor
        sy = cy + (sy - cy) / factor

    sx = np.clip(sx, 0, w - 1)
    sy = np.clip(sy, 0, h - 1)
    x0 = np.floor(sx).astype(np.int32)
    y0 = np.floor(sy).astype(np.int32)
    x1 = np.clip(x0 + 1, 0, w - 1)
    y1 = np.clip(y0 + 1, 0, h - 1)
    fx = (sx - x0)[..., None]
    fy = (sy - y0)[..., None]

    def sample(buf: np.ndarray) -> np.ndarray:
        # The alpha buffer is (h, w) while rgb is (h, w, 3), so it is promoted to
        # a single channel to keep one bilinear implementation for both.
        single = buf.ndim == 2
        source = buf[..., None] if single else buf
        top = source[y0, x0] * (1 - fx) + source[y0, x1] * fx
        bottom = source[y1, x0] * (1 - fx) + source[y1, x1] * fx
        out = top * (1 - fy) + bottom * fy
        return out[..., 0] if single else out

    return sample(rgb), sample(alpha)


# ---------------------------------------------------------------------------
# animations
# ---------------------------------------------------------------------------
def norm_grid(shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    h, w = shape
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    return xs / (w - 1), ys / (h - 1)


def render_pose(rgb: np.ndarray, alpha: np.ndarray, *, squash: float = 0.0,
                lift: float = 0.0, tilt: float = 0.0, ear: float = 0.0,
                breathe: float = 0.0, lean: float = 0.0,
                spin: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Build one frame from the base sprite.

    Every parameter is a small, named motion so an animation reads as a
    sequence of intent rather than a table of magic numbers:

    * ``squash``  vertical compression with matching horizontal spread, the
      classic squash-and-stretch. Positive squashes down.
    * ``lift``    whole-body vertical offset, in sprite heights.
    * ``tilt``    head/ear rotation in degrees, applied around the head centre.
    * ``ear``     ear-only flick, degrees.
    * ``breathe`` belly expansion, 0..1.
    * ``lean``    horizontal shear, for walking weight shift.
    * ``spin``    whole-body rotation in degrees, around the base centre.
    """
    h, w = alpha.shape
    xx, yy = norm_grid((h, w))
    zero = np.zeros_like(xx)

    dx = zero.copy()
    dy = zero.copy()
    scale = np.ones_like(xx)

    # --- squash and stretch -------------------------------------------------
    if squash:
        # Compress vertically, expand horizontally, pivoting on the ground line
        # so the character stays planted instead of sinking through the floor.
        k = 1.0 - squash
        scale *= 1.0 / max(0.2, k)
        dy += (yy - 1.0) * (1.0 - k) * h

    # --- breathing belly ----------------------------------------------------
    if breathe:
        belly = ellipse_weight(xx, yy, 0.52, 0.66, 0.40, 0.26, power=1.8)
        dy -= belly * breathe * 0.016 * h
        dx += belly * breathe * 0.010 * w * (xx - 0.5)

    # --- walking lean -------------------------------------------------------
    if lean:
        dx += (yy - 0.5) * lean * w * 0.06

    # --- head tilt and ear flick -------------------------------------------
    if tilt or ear:
        head_cx, head_cy = 0.50, 0.22
        head = ellipse_weight(xx, yy, head_cx, head_cy, 0.42, 0.32, power=1.6)
        if tilt:
            angle = math.radians(tilt)
            rx, ry = xx - head_cx, yy - head_cy
            # Rotate the *sample* position by -angle: a positive tilt moves the
            # drawn head clockwise.
            dx += head * (-(rx * (math.cos(angle) - 1) - ry * math.sin(angle))) * w
            dy += head * (-(rx * math.sin(angle) + ry * (math.cos(angle) - 1))) * h
        if ear:
            for ear_cx in (0.30, 0.70):
                region = ellipse_weight(xx, yy, ear_cx, 0.13, 0.16, 0.12, power=2.0)
                angle = math.radians(ear)
                rx, ry = xx - ear_cx, yy - 0.13
                dx += region * (-(rx * (math.cos(angle) - 1) - ry * math.sin(angle))) * w
                dy += region * (-(rx * math.sin(angle) + ry * (math.cos(angle) - 1))) * h

    # --- whole-body spin ----------------------------------------------------
    if spin:
        cx, cy = 0.5, 0.62
        angle = math.radians(spin)
        rx, ry = xx - cx, yy - cy
        dx += (-(rx * (math.cos(angle) - 1) - ry * math.sin(angle))) * w
        dy += (-(rx * math.sin(angle) + ry * (math.cos(angle) - 1))) * h

    # --- whole-body offset --------------------------------------------------
    if lift:
        dy -= lift * h

    return warp(rgb, alpha, dx, dy, scale)


# Every animation is a list of keyframes; `frames` is the number of rendered
# frames and the keys are placed evenly across it, then interpolated. Writing
# poses and letting the interpolator fill in keeps the intent legible — a
# hand-written 12-frame table is unreadable and unmaintainable.
ANIMATIONS: dict[str, dict] = {
    "idle": {
        "fps": 10,
        "keys": [
            {"breathe": 0.0, "lift": 0.000},
            {"breathe": 0.7, "lift": -0.004},
            {"breathe": 1.0, "lift": -0.006},
            {"breathe": 0.5, "lift": -0.002},
            {"breathe": 0.0, "lift": 0.000},
        ],
    },
    "breathe_deep": {
        "fps": 8,
        "keys": [
            {"breathe": 0.0, "squash": 0.0},
            {"breathe": 1.0, "squash": -0.020},
            {"breathe": 0.4, "squash": 0.008},
            {"breathe": 0.0, "squash": 0.0},
        ],
    },
    "ear_flick": {
        "fps": 12,
        "keys": [
            {"ear": 0, "tilt": 0},
            {"ear": -14, "tilt": -3},
            {"ear": 6, "tilt": 2},
            {"ear": 0, "tilt": 0},
        ],
    },
    "look_around": {
        "fps": 8,
        "keys": [
            {"tilt": 0, "lean": 0.0},
            {"tilt": -7, "lean": 0.35},
            {"tilt": 0, "lean": 0.0},
            {"tilt": 7, "lean": -0.35},
            {"tilt": 0, "lean": 0.0},
        ],
    },
    "hop": {
        "fps": 12,
        "keys": [
            {"lift": 0.000, "squash": 0.030},
            {"lift": -0.030, "squash": -0.045},
            {"lift": -0.075, "squash": -0.020},
            {"lift": -0.030, "squash": 0.035},
            {"lift": 0.000, "squash": 0.000},
        ],
    },
    "bounce_land": {
        "fps": 12,
        "keys": [
            {"lift": -0.070, "squash": -0.030},
            {"lift": 0.000, "squash": 0.075},
            {"lift": -0.018, "squash": -0.030},
            {"lift": 0.000, "squash": 0.030},
            {"lift": 0.000, "squash": 0.000},
        ],
    },
    "walk": {
        "fps": 12,
        "keys": [
            {"lean": 0.30, "lift": 0.000, "squash": 0.010},
            {"lean": 0.10, "lift": -0.012, "squash": -0.010},
            {"lean": -0.30, "lift": 0.000, "squash": 0.010},
            {"lean": -0.10, "lift": -0.012, "squash": -0.010},
            {"lean": 0.30, "lift": 0.000, "squash": 0.010},
        ],
    },
    "drag": {
        "fps": 10,
        "keys": [
            {"spin": 4, "squash": -0.030},
            {"spin": -5, "squash": 0.020},
            {"spin": 5, "squash": -0.030},
            {"spin": -4, "squash": 0.020},
            {"spin": 4, "squash": -0.030},
        ],
    },
    "sleep": {
        "fps": 6,
        "keys": [
            {"squash": 0.045, "tilt": 5, "breathe": 0.2},
            {"squash": 0.055, "tilt": 6, "breathe": 1.0},
            {"squash": 0.045, "tilt": 5, "breathe": 0.2},
        ],
    },
    "spin": {
        "fps": 12,
        "keys": [
            {"spin": 0}, {"spin": 90}, {"spin": 180}, {"spin": 270}, {"spin": 359},
        ],
    },
    "surprised": {
        "fps": 12,
        "keys": [
            {"lift": 0.000, "squash": 0.000, "ear": 0},
            {"lift": -0.050, "squash": -0.055, "ear": -18},
            {"lift": 0.000, "squash": 0.060, "ear": -10},
            {"lift": 0.000, "squash": 0.010, "ear": 0},
            {"lift": 0.000, "squash": 0.000, "ear": 0},
        ],
    },
    "happy": {
        "fps": 12,
        "keys": [
            {"lift": 0.000, "squash": 0.000, "ear": 0},
            {"lift": -0.022, "squash": -0.030, "ear": 10},
            {"lift": 0.000, "squash": 0.040, "ear": 4},
            {"lift": -0.014, "squash": -0.018, "ear": 8},
            {"lift": 0.000, "squash": 0.020, "ear": 0},
            {"lift": 0.000, "squash": 0.000, "ear": 0},
        ],
    },
    "angry": {
        "fps": 12,
        "keys": [
            {"shake": 0.0, "squash": 0.000},
            {"shake": 0.9, "squash": 0.035},
            {"shake": -0.9, "squash": 0.035},
            {"shake": 0.7, "squash": 0.030},
            {"shake": -0.7, "squash": 0.030},
            {"shake": 0.0, "squash": 0.000},
        ],
    },
}

# `shake` is horizontal only and reads better as its own key than as a lean,
# so it is folded into `lean` with a larger gain by the interpolator.
SHAKE_GAIN = 2.6


def interpolate(keys: list[dict], count: int) -> list[dict]:
    """Evenly resample a keyframe list to `count` frames, linearly."""
    if count <= 1:
        return [dict(keys[0])]
    out: list[dict] = []
    span = len(keys) - 1
    for index in range(count):
        t = index / (count - 1) * span
        low = min(int(math.floor(t)), span - 1) if span else 0
        high = min(low + 1, span)
        frac = t - low
        pose: dict[str, float] = {}
        for key in set(keys[low]) | set(keys[high]):
            a = float(keys[low].get(key, 0.0))
            b = float(keys[high].get(key, 0.0))
            pose[key] = a + (b - a) * frac
        out.append(pose)
    return out


def render_animation(name: str, spec: dict, rgb: np.ndarray, alpha: np.ndarray,
                     frame_count: int) -> list[Path]:
    out_dir = FRAMES / name
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.png"):
        stale.unlink()

    poses = interpolate(spec["keys"], frame_count)
    written: list[Path] = []
    for index, pose in enumerate(poses):
        if "shake" in pose:
            pose = dict(pose)
            pose["lean"] = pose.pop("shake") * SHAKE_GAIN
        warped_rgb, warped_alpha = render_pose(rgb, alpha, **pose)
        # Compose onto the fixed canvas at the ground line.
        canvas_rgb = np.ones((RENDER, RENDER, 3), dtype=np.float32)
        canvas_alpha = np.zeros((RENDER, RENDER), dtype=np.float32)
        h, w = warped_alpha.shape
        x = (RENDER - w) // 2
        y = int(GROUND_Y / CANVAS[1] * RENDER) - h
        x = max(0, min(x, RENDER - w))
        y = max(0, min(y, RENDER - h))
        canvas_rgb[y:y + h, x:x + w] = warped_rgb
        canvas_alpha[y:y + h, x:x + w] = warped_alpha
        frame = Image.fromarray(
            np.dstack([canvas_rgb * 255, canvas_alpha * 255]).astype(np.uint8), "RGBA")
        frame = frame.resize(CANVAS, Image.LANCZOS)
        path = out_dir / f"{index:02d}.png"
        frame.save(path)
        written.append(path)
    return written


def encode(name: str, fps: int) -> Path:
    """VP9 with alpha, through the same green-matte route as the art pipeline."""
    ASSETS.mkdir(parents=True, exist_ok=True)
    out = ASSETS / f"{name}.webm"
    vf = (
        "[0:v]format=rgba,split=2[c][m];"
        "[c]drawbox=x=0:y=0:w=iw:h=ih:color=0x00FF00@1.0:t=fill[cg];"
        "[cg][m]overlay=format=auto,format=rgba,"
        "colorkey=0x00FF00:0.22:0.03,format=yuva420p[out]"
    )
    subprocess.run([
        FFMPEG, "-y", "-loglevel", "error",
        "-framerate", str(fps), "-i", str(FRAMES / name / "%02d.png"),
        "-filter_complex", vf, "-map", "[out]",
        "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
        "-b:v", "0", "-crf", "30", "-auto-alt-ref", "0", "-row-mt", "1",
        "-metadata:s:v:0", "alpha_mode=1", "-an", str(out),
    ], check=True)
    return out


def make_preview(name: str, size: int = 180) -> Path:
    """A looping GIF for the README, on a neutral panel.

    Flattened to RGB *before* the palette conversion: quantising straight from
    RGBA leaves the unused alpha byte in the palette index and produces magenta
    speckle in the preview.
    """
    preview_dir = ROOT / "docs" / "preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    files = sorted((FRAMES / name).glob("*.png"))
    frames = []
    for path in files:
        sprite = Image.open(path).convert("RGBA")
        background = Image.new("RGBA", sprite.size, (30, 32, 38, 255))
        background.alpha_composite(sprite)
        flat = background.convert("RGB").resize((size, size), Image.LANCZOS)
        frames.append(flat.convert("P", palette=Image.ADAPTIVE, colors=128))
    out = preview_dir / f"{name}.gif"
    spec = ANIMATIONS.get(name, {})
    # The GIF delay is per frame and in milliseconds; deriving it from the
    # authored fps keeps the preview playing at the same speed as the pet.
    delay = max(20, round(1000 / spec.get("fps", FPS)))
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=delay, loop=0, optimize=True)
    return out


def main() -> None:
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    # 12 frames rather than 8: the keyframes are interpolated linearly, so frame
    # count is what decides whether a squash reads as motion or as a jump. At 8
    # the hop visibly steps; at 12 it reads as continuous, and the whole set
    # still comes to around 600 KiB. Raising it further buys little at the size
    # the pet is actually displayed.
    frame_count = 12
    if "--frames" in sys.argv:
        frame_count = int(sys.argv[sys.argv.index("--frames") + 1])

    rgb, alpha = load_sprite("base")
    print(f"sprite: {rgb.shape[1]}x{rgb.shape[0]} source pixels, "
          f"rendered at {RENDER}px, output {CANVAS[0]}x{CANVAS[1]}")

    wanted = argv or list(ANIMATIONS)
    manifest = {}
    for name in wanted:
        spec = ANIMATIONS.get(name)
        if spec is None:
            print(f"  ! unknown animation {name!r}, skipped")
            continue
        frames = render_animation(name, spec, rgb, alpha, frame_count)
        webm = encode(name, spec.get("fps", FPS))
        preview = make_preview(name)
        manifest[name] = {
            "frames": len(frames),
            "fps": spec.get("fps", FPS),
            "keys": spec["keys"],
            "bytes": webm.stat().st_size,
            "preview": preview.name,
        }
        print(f"  {name:14s} {len(frames):2d} frames @ {spec.get('fps', FPS)}fps  "
              f"{webm.stat().st_size / 1024:6.1f} KiB webm  "
              f"{preview.stat().st_size / 1024:4.0f} KiB gif")
    (FRAMES.parent / "motion-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = sum(entry["bytes"] for entry in manifest.values()) / 1024
    print(f"\n{len(manifest)} animations in {ASSETS}  ({total:.0f} KiB total)")


if __name__ == "__main__":
    main()
