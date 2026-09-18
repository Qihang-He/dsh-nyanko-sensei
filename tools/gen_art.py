#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Nyanko-sensei desktop-pet asset pipeline — stage 1: character sheet.

The whole project's visual consistency hangs on one thing: every frame is
generated from the *same* written character block (CHAR) so the model keeps the
calico markings in the same places. This script renders the reference views and
the first action sheets, writing them under ``work/`` (intermediate, git-ignored)
so later stages can consume them.

The generation backend is chosen by `tools/imggen.py` from whichever credential
is configured (Google AI Studio, OpenRouter, or the OfoxAI relay), so moving
provider is an environment change rather than a code change.

Usage:
    python gen_art.py sheet                    # reference views
    python gen_art.py actions [ids]            # action pose sheets
    python gen_art.py sheet --backend google   # force a backend
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from imggen import DEFAULT_MODEL, generate as generate_image, pick  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"

# Model per backend. The Gemini 3 Pro image model produced by far the best
# likeness of the six tried in tools/candidates.py, but it is not offered by
# every backend, so each has its own default and the best available wins.
MODEL = "google/gemini-3-pro-image"
MODEL_BY_BACKEND = {
    "google": "gemini-3-pro-image",
    "openrouter": "google/gemini-3-pro-image",
    "ofox": "google/gemini-3-pro-image",
}
# Google AI Studio's free tier is narrower than the paid catalog; fall back
# rather than 404 on a model the key cannot reach.
MODEL_FALLBACK = {
    "google": ["gemini-3-pro-image", "gemini-2.5-flash-image"],
}

# --------------------------------------------------------------------------
# The identity anchor. Descriptive only — no franchise names — because a
# named-character reproduction request is refused by the image model, and the
# visual description is what actually pins the markings down anyway.
#
# Revision 2. The first attempt produced a generic round calico mascot: a
# sphere with dot eyes, which is not the character at all. What was wrong, and
# what this block now says instead:
#
#   * silhouette  - a ball. Now a plump EGG / pear: shoulders narrower than the
#                   hips, rump heavy, belly low, four clearly visible short
#                   legs. Plump, not spherical.
#   * face        - round with big round eyes. Now a FLATTENED WIDE face, narrow
#                   slit eyes and large pointed ears.
#   * markings    - scattered, random calico. Now a fixed layout, stated from
#                   the viewer's side so it cannot mirror: THREE BANDS across
#                   the forehead (wide orange, thin white divider, wide dark
#                   grey), grey continuing down over the right ear, orange over
#                   the left shoulder and flank, white chest and paws, plus the
#                   dark collar and gold bell the first revision omitted.
#   * tail        - invented dark rings. Nothing about the tail markings is
#                   asserted now: it is short and stubby, and banding is
#                   explicitly forbidden rather than described.
#
# Calibrated against the reference stills in work/ref/ (not shipped: they are
# third-party frames kept locally for comparison only). The trait-by-trait
# comparison is recorded in tools/CALIBRATION.md, and tools/critique.py turns
# that table into a visual self-check.
# --------------------------------------------------------------------------
CHAR = (
    "a plump calico cat character from a Japanese anime TV series, drawn in "
    "clean flat cel-shaded 2D animation style with a firm black outline. "
    # Silhouette first: this is the single thing the first revision got most
    # wrong, so it is stated before anything else and in the negative too.
    "Body shape: an EGG — narrow at the shoulders, widest at the hips, with a "
    "heavy low belly, a big round rump and four short but clearly visible legs "
    "with distinct white paw tips. Plump and rounded overall, but NEVER a "
    "perfect sphere and never a ball with no legs. Tiny short tail. "
    # Head.
    "Head: wide and rather FLAT, not a circle; the face is broader than it is "
    "tall and sits directly on the body with no visible neck. Ears are LARGE, "
    "TALL, pointed triangular cat ears angled slightly outward. Muzzle: a small "
    "white rounded muzzle with a tiny pink-black triangular nose and a thin "
    "simple mouth line. "
    # The eyes deliberately contradict the first revision, which drew big round
    # golden irises. The character's eyes are almost always drawn as narrow slits
    # or closed crescents, so what they are NOT matters more here than what they
    # are.
    "Eyes: NARROW, thin, curved slit-like eyes that read as half-closed or "
    "closed in a sly smile; the golden-yellow iris is at most a small sliver, "
    "never a big round cartoon eye. The expression reads as sly, smug or mildly "
    "unimpressed. "
    # The signature marking layout. Read off the reference images at 3x zoom,
    # which is the only way the forehead detail is visible at all: it is THREE
    # bands, not two patches, and the thin white divider between them is what
    # makes the head read as this character rather than as a generic calico.
    "Fur pattern, IDENTICAL in every image and never mirrored — the body is "
    "mostly WHITE. The head carries the signature THREE BANDS across the "
    "forehead, in this left-to-right order as the viewer sees them: first a "
    "WIDE ORANGE band over the left half, then a NARROW WHITE VERTICAL DIVIDER "
    "running straight down the centre of the forehead between the ears, then a "
    "WIDE DARK-GREY band over the right half which continues down over the "
    "right ear and the right side of the head. That thin white divider is "
    "essential and must be clearly visible. The muzzle and the area around "
    "both eyes stay white. On the body, a large ORANGE patch covers the back, "
    "the shoulder and the flank on the viewer's LEFT side, while DARK GREY "
    "covers the upper back and the rump on the viewer's RIGHT side; the chest, "
    "the belly and all four paws are clean white. "
    "Around its neck it wears a thin, dark collar with a small round GOLD BELL "
    "hanging at the front. "
    # Cheek marks are expression-dependent, so they are marked optional: forcing
    # them into every frame would fight the poses where the reference does not
    # show them, and the model would start inventing them on the body too.
    "When its face is drawn in the happy, sly or embarrassed expression, add "
    "three short red-orange diagonal strokes on each cheek and a thin curved "
    "mouth line. "
    # Naming the traps explicitly, because the model reaches for these by default.
    "Do NOT draw a tabby: no stripes anywhere on the head, body, legs or tail. "
    "Do NOT ring or band the tail like a raccoon. Do NOT give it long thin "
    "legs, a pointed snout, a long neck, or large round cartoon eyes. "
)

# Identity for the giant white beast form, likewise description-only.
BEAST = (
    "a huge majestic white wolf-fox beast spirit, Japanese anime "
    "TV-animation style, clean thick black outlines, flat cel-shaded colors, "
    "long flowing white fur, a long white tail, golden eyes, dark red markings "
    "on its forehead and around the eyes, elegant and imposing, "
)

BG = (" completely flat pure chroma-key green background, uniformly #00FF00 "
      "right up to all four edges of the image, with ABSOLUTELY NO shadow of any "
      "kind: no drop shadow, no contact shadow, no cast shadow on the ground, no "
      "floor, no horizon line, no vignette and no gradient. The green must remain "
      "the identical pure green everywhere the character is not.")

STYLE_TAIL = (
    " Full body, centered, facing the camera, standing on the ground, entirely "
    "inside the frame with a clear margin of green on all four sides, 1:1 square "
    "composition, consistent scale and camera distance."
)


def sheet_prompt(cells: list[str], subject: str = CHAR, note: str = "") -> str:
    """Build a 2x2 sprite-sheet prompt with one pose per cell."""
    rows = []
    for index, cell in enumerate(cells):
        slot = ["top-left", "top-right", "bottom-left", "bottom-right"][index]
        rows.append(f"{slot} quadrant: {cell}")
    return (
        "Generate a single square image that is a 2x2 grid sprite sheet, divided "
        "into four equal quadrants by thin white gutters, and inside each quadrant "
        "draw exactly ONE full-body view of the SAME character. Do not write any "
        "text or numbers anywhere in the image.\n\n"
        f"Character: {subject}{BG}\n\n"
        "Four quadrants, in this order:\n"
        + "\n".join(rows)
        + "\n\nEvery quadrant must show the identical character with identical "
        "colors and markings, the identical size and the identical camera angle, "
        "standing on the same ground line near the bottom of its quadrant."
        + ("\n\n" + note if note else "")
    )


# --------------------------------------------------------------------------
# Reference views: one image each, used as the identity reference for humans
# reviewing the result and as an input for later image-to-image work.
# --------------------------------------------------------------------------
SHEET_VIEWS = {
    "front": f"front view, standing, facing the camera, tail visible behind"
             + STYLE_TAIL,
    "side": f"full side profile view, facing right, standing on all fours"
            + STYLE_TAIL,
    "sit": f"sitting upright on its haunches, front paws together, facing the camera"
           + STYLE_TAIL,
    "sleep": "curled up asleep on the ground, eyes closed, tail wrapped around itself"
             + STYLE_TAIL,
    "beast_front": "front view of the giant white beast form standing on all fours, "
                   "tail raised" + STYLE_TAIL,
    "beast_side": "side profile of the giant white beast form, facing right, standing"
                  + STYLE_TAIL,
}

# --------------------------------------------------------------------------
# Actions. Each entry is one 2x2 sheet; the four quadrants become four frames
# of one looping animation. Frame order matters: it is the playback order.
# --------------------------------------------------------------------------
ACTIONS: dict[str, dict] = {
    "idle": {
        "frames": [
            "front view, standing still, eyes open, tail relaxed down",
            "front view, standing, body slightly compressed downward (natural breathing squash), eyes half-closed",
            "front view, standing still, eyes closed (mid blink), tail flicked slightly to one side",
            "front view, standing, body slightly stretched upward, eyes open wide",
        ],
    },
    "walk": {
        "frames": [
            "front view, mid-stride with its left front paw lifted off the ground, body tilted a little to the right",
            "front view, all four paws on the ground, body compressed slightly (step contact)",
            "front view, mid-stride with its right front paw lifted off the ground, body tilted a little to the left",
            "front view, all four paws on the ground, body compressed slightly (step contact)",
        ],
    },
    "blink": {
        "frames": [
            "front view, standing, eyes wide open, ears up, tail still",
            "front view, standing, eyes half closed mid-blink, ears up",
            "front view, standing, eyes fully closed in a blink, ears up",
            "front view, standing, eyes half open returning from the blink, ears up",
        ],
    },
    "sit": {
        "frames": [
            "sitting upright on its haunches, front paws together, eyes open, ears up",
            "sitting upright, tail tip lifted and curled slightly",
            "sitting upright, eyes half closed, looking content",
            "sitting upright, one ear twitching downward a little",
        ],
    },
    "yawn": {
        "frames": [
            "standing, eyes half closed, mouth beginning to open",
            "standing, mouth wide open in a big yawn, eyes squeezed shut",
            "standing, mouth still open, tongue slightly visible, head tilted back",
            "standing, mouth closed again, eyes half open, looking sleepy",
        ],
    },
    "sleep": {
        "frames": [
            "curled up asleep on the ground, eyes closed, tail wrapped around itself, body rounded",
            "curled up asleep, body compressed slightly downward (breathing in)",
            "curled up asleep, body slightly expanded upward (breathing out), tail tip twitching",
            "curled up asleep, body relaxed, one ear drooping",
        ],
    },
    "happy": {
        "frames": [
            "standing, both ears perked up high, eyes bright and wide, tail raised",
            "standing and hopping slightly upward with all paws off the ground, ears perked, eyes happily closed",
            "landing on the ground with body squashed wider and flatter (squash on landing), tail up",
            "standing again, stretching upward slightly, eyes sparkling, tail curled high in a question-mark shape",
        ],
    },
    "angry": {
        "frames": [
            "standing, ears flattened back, eyes narrowed into a glare, fur bristled, mouth in a small frown",
            "standing, ears flattened, one front paw raised as if swatting, mouth open showing small fangs",
            "standing, body puffed up larger and rounder, tail bristled and raised, glaring",
            "standing, body settling back to normal size, still glaring, tail swishing to one side",
        ],
    },
    "surprised": {
        "frames": [
            "standing, ears snapped straight up, eyes wide open, body frozen",
            "standing, body jumped slightly upward off the ground with limbs splayed out in a star shape",
            "landing, body squashed flat and wide, eyes still wide, mouth open in a small 'o'",
            "standing again, ears slowly relaxing, eyes wide but calming down",
        ],
    },
    "eat": {
        "frames": [
            "sitting, holding a small white rice ball in both front paws, eyes bright",
            "sitting, mouth wide open taking a big bite of the rice ball, crumbs in the air",
            "sitting, cheeks puffed out full of food, eyes squeezed shut with enjoyment",
            "sitting, licking its lips with its tongue out, rice ball almost gone",
        ],
    },
    "drag": {
        "frames": [
            "front view with all four legs dangling limply downward below the body, tail hanging, eyes wide and startled",
            "front view with all four legs dangling, body tilted a little to the left, ears blown back",
            "front view with all four legs dangling, body tilted a little to the right, tail flicked upward",
            "front view with all four legs dangling, squirming, eyes comically annoyed",
        ],
    },
    "beast": {
        "frames": [
            "front view of the giant white beast form standing on all fours, head lowered, tail sweeping",
            "side view of the giant white beast form, mane and tail flowing upward",
            "front view of the giant white beast form, head raised and roaring with mouth open, tail up high",
            "side view of the giant white beast form leaping forward, front paws off the ground, tail streaming behind",
        ],
        "subject": BEAST,
    },
}


def _resolve_model(backend_id: str) -> list[str]:
    """Models to try for the active backend, best likeness first."""
    return MODEL_FALLBACK.get(backend_id) or [MODEL_BY_BACKEND.get(backend_id, MODEL)]


def _extension_for(data: bytes) -> str:
    """Extension matching the actual bytes, not the extension we wish for."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:2] == b"\xff\xd8":
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def sheet_path(out_dir: Path, name: str) -> Path | None:
    """The already-rendered sheet for `name`, whichever extension it landed with."""
    for suffix in (".png", ".jpg", ".webp"):
        candidate = out_dir / f"{name}{suffix}"
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    return None


def render_sheet(name: str, frames: list[str], subject: str, out_dir: Path,
                 backend: str | None = None) -> Path:
    cached = sheet_path(out_dir, name)
    if cached is not None:
        print(f"  = {name} (cached)")
        return cached

    prompt = sheet_prompt(frames, subject=subject)
    (out_dir / f"{name}.prompt.txt").write_text(prompt, encoding="utf-8")
    print(f"  > {name} ...", flush=True)
    started = time.time()

    active = pick(backend)
    models = _resolve_model(active.id)
    data, last = None, None
    for index, model in enumerate(models):
        try:
            # Written to a temporary name because the extension can only be
            # chosen once the bytes are known; the backend is told nothing about
            # the file name, so asking for a .png and getting JPEG is normal.
            data = generate_image(prompt, model=model, backend=backend)
            break
        except Exception as exc:  # noqa: BLE001 - try the next model, then give up
            last = exc
            if index + 1 < len(models):
                print(f"    ! {model} failed ({str(exc)[:90]}); trying next model")
    if data is None:
        raise RuntimeError(f"{name}: every model failed: {last}")

    out = out_dir / f"{name}{_extension_for(data)}"
    out.write_bytes(data)
    print(f"    {out.name} {out.stat().st_size / 1024:.0f} KiB "
          f"in {time.time() - started:.1f}s via {active.id}")
    return out


def parse_args() -> tuple[str, str | None, list[str]]:
    """Split argv into (mode, backend, positional ids).

    Kept hand-rolled rather than argparse so `--backend` can sit anywhere, which
    matters when the same command line is reused by hand and from build-all.cmd.
    """
    argv = sys.argv[1:]
    backend = None
    if "--backend" in argv:
        index = argv.index("--backend")
        if index + 1 >= len(argv):
            raise SystemExit("--backend needs a value (google | openrouter | ofox)")
        backend = argv[index + 1]
        del argv[index:index + 2]
    mode = argv[0] if argv else "sheet"
    return mode, backend, argv[1:]


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    mode, backend, wanted = parse_args()

    if mode == "sheet":
        out_dir = WORK / "views"
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, pose in SHEET_VIEWS.items():
            subject = BEAST if name.startswith("beast") else CHAR
            render_sheet(name, [pose, pose, pose, pose], subject, out_dir, backend)
        return

    if mode == "actions":
        out_dir = WORK / "sheets"
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest = {}
        for name in (wanted or list(ACTIONS)):
            spec = ACTIONS[name]
            render_sheet(name, spec["frames"], spec.get("subject", CHAR), out_dir, backend)
            manifest[name] = spec["frames"]
        (WORK / "actions.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    raise SystemExit(f"unknown mode: {mode!r}; expected 'sheet' or 'actions'")


if __name__ == "__main__":
    main()
