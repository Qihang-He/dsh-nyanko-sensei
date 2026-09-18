#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Nyanko-sensei desktop-pet asset pipeline — stage 2: sheet → transparent frames.

One generated 2x2 sprite sheet becomes four animation frames, in this order:

    split quadrants → chroma-key the flat green background to alpha
    → trim to the character's bounding box
    → normalize scale across the action's frames (median reference)
    → anchor to a common ground line / centre
    → write aligned RGBA frames

Alignment is what makes or breaks the illusion. Each action's frames are scaled
so the *median* character height matches TARGET_H, then anchored by pose family:
standing poses sit on ``GROUND_Y``, perched poses are centred on it so a sitting
or curled-up cat still rests on the same line.

Usage:
    python build_assets.py frames [action ...]   # sheets → work/frames/<action>/
    python build_assets.py encode [action ...]   # frames → assets/anims/<action>.webm
    python build_assets.py preview               # README animation GIFs
    python build_assets.py all
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
FRAMES = WORK / "frames"
ASSETS = ROOT / "assets" / "anims"
PREVIEW = ROOT / "docs" / "preview"

# Final animation canvas. 360x360 at the pet's default on-screen width reads as
# a crisp 1x sprite; the ground line sits low so the cat looks like it stands on
# the bottom edge of its own box.
CANVAS_W, CANVAS_H = 360, 360
TARGET_H = 300
GROUND_Y = 340

# Pose families decide the vertical anchor. "stand" rests its feet on the ground
# line; "perch" (sitting, curled up, floating) centres on the same line.
PERCH_ACTIONS = {"sit", "sleep", "eat", "drag"}

FFMPEG = shutil.which("ffmpeg") or r"D:\ffmpeg-2026-05-28-git-7b46c6a2a3-essentials_build\bin\ffmpeg.exe"
# ffprobe normally sits beside ffmpeg; resolve it the same way rather than by
# string surgery on the ffmpeg path, which is wrong when the build ships the
# executable under a different name (`ffmpeg.EXE` on some Windows builds).
FFPROBE = shutil.which("ffprobe") or str(Path(FFMPEG).with_name(
    "ffprobe.exe" if Path(FFMPEG).suffix.lower() == ".exe" else "ffprobe"))


# ---------------------------------------------------------------------------
# sheet → quadrants
# ---------------------------------------------------------------------------
def split_sheet(path: Path) -> list[Image.Image]:
    """Cut a 2x2 sheet into four RGB quadrants, trimming the white gutters."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    # The model draws thin white gutters between cells; inset the cut by 2% so
    # no gutter pixel survives into a frame.
    inset_x, inset_y = int(w * 0.02), int(h * 0.02)
    boxes = []
    for row in range(2):
        for col in range(2):
            left = col * w // 2 + inset_x
            upper = row * h // 2 + inset_y
            right = (col + 1) * w // 2 - inset_x
            lower = (row + 1) * h // 2 - inset_y
            boxes.append((left, upper, right, lower))
    return [img.crop(b) for b in boxes]


# ---------------------------------------------------------------------------
# chroma key
# ---------------------------------------------------------------------------
def chroma_to_alpha(rgb: Image.Image, screen: tuple[float, float, float] | None = None,
                    dominance_threshold: float = 18.0,
                    near_threshold: float = 150.0) -> Image.Image:
    """Replace a flat colour screen with alpha, whatever colour the screen is.

    The screen colour is measured from the image border rather than assumed, and
    the "is this background?" test is written in terms of that measurement. That
    matters because the earlier version of this function hard-coded *green*
    dominance — a pixel counted as screen only if green exceeded both other
    channels — which is correct for a green screen and silently useless for any
    other colour: asked to key magenta, it kept 100% of the frame and reported a
    full-frame character.

    Two ramps multiply, and both are needed:

    * **distance** from the measured screen colour, which is what identifies the
      flat background and tolerates the slight variance a model renders it with;
    * **saturation relative to the screen**, which stops the ramp from eating
      low-contrast artwork that happens to sit near the screen colour in absolute
      terms.

    Screening on saturation rather than on a fixed channel is what makes the
    function colour-agnostic: magenta, green and blue screens all work, and a
    screen colour can be passed in explicitly when it is known.
    """
    arr = np.asarray(rgb, dtype=np.float32)
    h, w, _ = arr.shape
    if screen is None:
        band = max(2, int(min(h, w) * 0.02))
        border = np.concatenate([
            arr[:band].reshape(-1, 3), arr[-band:].reshape(-1, 3),
            arr[:, :band].reshape(-1, 3), arr[:, -band:].reshape(-1, 3),
        ])
        screen = tuple(np.median(border, axis=0))
    screen_arr = np.array(screen, dtype=np.float32)

    dist = np.sqrt(((arr - screen_arr) ** 2).sum(axis=2))

    # How saturated is this pixel, and how saturated is the screen? A screen is
    # by construction a vivid flat colour; the character is cream, brown and grey.
    def saturation(buf: np.ndarray) -> np.ndarray:
        mx = buf.max(axis=-1)
        mn = buf.min(axis=-1)
        return np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)

    sat = saturation(arr)
    screen_sat = float(saturation(screen_arr.reshape(1, 1, 3))[0, 0])
    # Pixels at least this saturated can be screen; well below the screen's own
    # saturation, so anti-aliased edges still fade rather than cut.
    sat_ramp = np.clip((sat - screen_sat * 0.28) / max(1e-6, screen_sat * 0.30), 0.0, 1.0)
    dist_ramp = np.clip((near_threshold - dist) / 70.0, 0.0, 1.0)
    background = sat_ramp * dist_ramp

    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., :3] = _despill(arr, screen_arr, background, 1.0 - background).astype(np.uint8)
    out[..., 3] = np.clip((1.0 - background) * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _despill(arr: np.ndarray, screen: np.ndarray, background: np.ndarray,
             alpha: np.ndarray, strength: float = 40.0) -> np.ndarray:
    """Remove screen contamination from the pixels that survive the key.

    A chroma key answers "is this pixel background?" but a model asked for a
    coloured screen does not keep that colour out of the artwork: it tints the
    outline and the anti-aliased edge with it. Those pixels are mostly character,
    so the key correctly keeps them — and they then read as a coloured fringe
    around the sprite once it is composited over a page.

    Written against the measured screen colour rather than against green. The
    first version of this function only ever lowered the green channel, which is
    correct for a green screen and does nothing at all for a magenta one — the
    measured magenta tint on a real output was 70 units and the green-only
    version left every unit of it in place.

    For each pixel, whichever channel the screen dominates is the channel pulled
    down toward the other two. `strength` is a 0..255 allowance for genuinely
    saturated artwork, and it is calibrated against this character: the gold bell
    and eyes reach a green excess of 13 against a key threshold of 18, so an
    allowance of 40 cannot flatten them.

    Weighted by `alpha`, which matters: a semi-transparent edge pixel *should*
    carry the screen colour, because the matte already tells the compositor how
    much of it to show. Recolouring those would darken the outline into a hard
    rim.
    """
    out = arr.astype(np.float32).copy()
    screen = screen.astype(np.float32)
    # The channel the screen lives in, and its two companions.
    channel = int(np.argmax(screen))
    others = [i for i in range(3) if i != channel]
    ceiling = np.maximum(out[..., others[0]], out[..., others[1]]) + strength
    excess = np.clip(out[..., channel] - ceiling, 0.0, None)
    out[..., channel] -= excess * np.clip(alpha, 0.0, 1.0)
    return out


def content_box(rgba: Image.Image, threshold: int = 16) -> tuple[int, int, int, int]:
    """Bounding box of the pixels that survived the key."""
    alpha = np.asarray(rgba)[..., 3]
    ys, xs = np.where(alpha > threshold)
    if len(xs) == 0:
        return (0, 0, rgba.width, rgba.height)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


# ---------------------------------------------------------------------------
# frames
# ---------------------------------------------------------------------------
def build_frames(action: str, sheet: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.png"):
        stale.unlink()

    quadrants = split_sheet(sheet)
    keyed = [chroma_to_alpha(q) for q in quadrants]
    boxes = [content_box(k) for k in keyed]
    heights = [b[3] - b[1] for b in boxes]
    widths = [b[2] - b[0] for b in boxes]
    ref_h = float(np.median(heights)) or 1.0
    scale = TARGET_H / ref_h

    perch = action in PERCH_ACTIONS
    for index, (image, box) in enumerate(zip(keyed, boxes)):
        scale_i = scale
        # Guard against one wildly mis-scaled cell hijacking the sequence: a
        # frame more than 25% off the median is rescaled on its own terms.
        if abs((box[3] - box[1]) - ref_h) / ref_h > 0.25 and box[3] > box[1]:
            scale_i = TARGET_H / float(box[3] - box[1])

        crop = image.crop(box)
        new_size = (max(1, round(crop.width * scale_i)), max(1, round(crop.height * scale_i)))
        crop = crop.resize(new_size, Image.LANCZOS)

        canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        left = round((CANVAS_W - crop.width) / 2)
        if perch:
            top = round(GROUND_Y - crop.height / 2)
        else:
            top = round(GROUND_Y - crop.height)
        canvas.alpha_composite(crop, (left, top))
        canvas.save(out_dir / f"{index:02d}.png")

    return {
        "action": action,
        "frames": len(quadrants),
        "sheet": str(sheet.relative_to(ROOT)).replace("\\", "/"),
        "source_sizes": [[b[2] - b[0], b[3] - b[1]] for b in boxes],
        "scale": round(scale, 4),
        "perch": perch,
    }


def load_frames(action: str) -> list[Path]:
    d = FRAMES / action
    files = sorted(p for p in d.glob("*.png"))
    if not files:
        raise SystemExit(f"no frames for {action!r}; run `build_assets.py frames` first")
    return files


# ---------------------------------------------------------------------------
# encode
# ---------------------------------------------------------------------------
def encode_webm(action: str, fps: int = 10) -> Path:
    """Encode aligned RGBA PNGs into a VP9-with-alpha WebM via a green matte.

    VP9 carries alpha in a side data plane that ffmpeg's ``yuva420p`` input does
    not populate, so the alpha travels through a chroma key instead:

        RGBA frames  ->  flatten onto pure green  ->  colorkey the green out
                     ->  back to RGBA  ->  yuva420p  ->  libvpx-vp9

    ``colorkey`` rather than ``chromakey`` on purpose: ``chromakey`` only
    rewrites the colour planes (its alpha handling is a blend, not a mask), so
    the encoder was handed an opaque stream and ffprobe reported ``yuv420p``.
    ``colorkey`` sets the alpha channel itself, which is what survives into the
    container.
    """
    files = load_frames(action)
    ASSETS.mkdir(parents=True, exist_ok=True)
    out = ASSETS / f"{action}.webm"
    pattern = str(FRAMES / action / "%02d.png")
    vf = (
        "[0:v]format=rgba,split=2[c][m];"
        "[c]drawbox=x=0:y=0:w=iw:h=ih:color=0x00FF00@1.0:t=fill[cg];"
        "[cg][m]overlay=format=auto,format=rgba,"
        "colorkey=0x00FF00:0.22:0.03,format=yuva420p[out]"
    )
    cmd = [
        FFMPEG, "-y", "-loglevel", "error",
        "-framerate", str(fps), "-i", pattern,
        "-filter_complex", vf, "-map", "[out]",
        "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
        "-b:v", "0", "-crf", "30",
        "-auto-alt-ref", "0", "-row-mt", "1",
        # alpha_mode is what a browser actually looks for to composite the pet
        # over the page; libvpx writes it, but naming it makes the intent and
        # the contract explicit.
        "-metadata:s:v:0", "alpha_mode=1",
        "-an", str(out),
    ]
    subprocess.run(cmd, check=True)
    return out


def probe_alpha(path: Path) -> dict:
    """Decode one frame and measure its alpha, rather than trusting ``pix_fmt``.

    ffmpeg stores VP9 alpha as a side plane and reports the stream as
    ``yuv420p`` with an ``alpha_mode=1`` tag, so a pixel-format probe looks
    negative even when the file is correct. Measuring the decoded alpha channel
    is the only honest check.
    """
    info = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,nb_frames:stream_tags=alpha_mode",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    stream = json.loads(info.stdout)["streams"][0]

    # Alpha must be decoded by the libvpx decoder explicitly: ffmpeg's native
    # VP9 decoder silently drops the alpha side plane, which makes a perfectly
    # good file look opaque. This is the trap that makes people delete working
    # assets, so the probe pins the decoder.
    decoded = subprocess.run(
        [FFMPEG, "-v", "error", "-c:v", "libvpx-vp9", "-i", str(path),
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
        capture_output=True, check=True).stdout
    alpha = np.frombuffer(decoded, dtype=np.uint8)
    if alpha.size % 4 == 0 and alpha.size >= 4:
        alpha = alpha.reshape(-1, 4)[:, 3]
    transparent = float((alpha < 16).mean()) if alpha.size else 0.0
    # ffprobe reports stream tag keys upper-cased; look the tag up case-insensitively.
    tags = {str(k).lower(): v for k, v in (stream.get("tags") or {}).items()}
    stream["alpha_mode"] = tags.get("alpha_mode")
    stream["transparent_ratio"] = round(transparent, 4)
    stream["has_alpha"] = transparent > 0.05
    return stream


# ---------------------------------------------------------------------------
# previews
# ---------------------------------------------------------------------------
def make_preview(action: str, size: int = 180) -> Path:
    """A small looping GIF for the README, composited on a neutral dark panel.

    The composite is flattened to RGB *before* the palette conversion: quantising
    straight from RGBA leaves the unused alpha byte in the palette index and
    produces magenta speckle in the preview.
    """
    files = load_frames(action)
    PREVIEW.mkdir(parents=True, exist_ok=True)
    frames = []
    for f in files:
        sprite = Image.open(f).convert("RGBA")
        bg = Image.new("RGBA", sprite.size, (30, 32, 38, 255))
        bg.alpha_composite(sprite)
        flat = bg.convert("RGB").resize((size, size), Image.LANCZOS)
        frames.append(flat.convert("P", palette=Image.ADAPTIVE, colors=128))
    out = PREVIEW / f"{action}.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=120, loop=0, optimize=True)
    return out


# ---------------------------------------------------------------------------
def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    sheets = WORK / "sheets"
    actions = sorted(p.stem for p in sheets.glob("*.png")) + \
              sorted(p.stem for p in sheets.glob("*.jpg"))
    if len(sys.argv) > 2:
        actions = sys.argv[2:]

    if mode in ("frames", "all"):
        manifest = []
        for action in actions:
            sheet = next((p for p in (sheets / f"{action}.png", sheets / f"{action}.jpg") if p.exists()), None)
            if sheet is None:
                print(f"  ! {action}: no sheet, skipped")
                continue
            info = build_frames(action, sheet, FRAMES / action)
            manifest.append(info)
            print(f"  frames {action}: {info['frames']} @ scale {info['scale']}")
        (WORK / "frames-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if mode in ("encode", "all"):
        failed = []
        for action in actions:
            webm = encode_webm(action)
            info = probe_alpha(webm)
            verdict = "alpha OK" if info.get("has_alpha") else "NO ALPHA"
            print(f"  webm {action}: {webm.stat().st_size / 1024:.0f} KiB "
                  f"{info.get('width')}x{info.get('height')} "
                  f"alpha_mode={info.get('alpha_mode')} "
                  f"transparent={info.get('transparent_ratio')} [{verdict}]")
            if not info.get("has_alpha"):
                failed.append(action)
        if failed:
            raise SystemExit(f"encoded without a usable alpha channel: {', '.join(failed)}")

    if mode in ("preview", "all"):
        for action in actions:
            gif = make_preview(action)
            print(f"  gif  {action}: {gif.stat().st_size / 1024:.0f} KiB")


if __name__ == "__main__":
    main()
