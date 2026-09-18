#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Nyanko-sensei desktop-pet asset pipeline — stage 1: character sheet.

The whole project's visual consistency hangs on one thing: every frame is
generated from the *same* written character block (CHAR) so the model keeps the
calico markings in the same places. This script renders the reference views and
the first action sheets, writing them under ``work/`` (intermediate, git-ignored)
so later stages can consume them.

Usage:
    python gen_art.py sheet          # reference views (front/side/sit/beast)
    python gen_art.py actions [ids]  # action pose sheets
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ofox import generate_image  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
# Chosen by eye from the shortlist in tools/candidates.py: the roundest body,
# the shortest legs and the closest facial expression of the six models tried.
MODEL = "google/gemini-3-pro-image"

# --------------------------------------------------------------------------
# The identity anchor. Descriptive only — no franchise names — because a
# named-character reproduction request is refused by the image model, and the
# visual description is what actually pins the markings down anyway.
# --------------------------------------------------------------------------
CHAR = (
    "a very fat, perfectly round chubby calico cat mascot character, Japanese "
    "anime TV-animation style, clean thick black outlines, flat cel-shaded "
    "colors, large friendly slightly narrowed eyes with golden yellow irises and "
    "vertical slit pupils, a small triangular pink-lined nose, two short "
    "triangular upright ears, very short stubby legs, no visible neck, head "
    "almost as wide as the body. "
    # The marking layout, stated once from the viewer's point of view so the
    # image model cannot mirror it: this is the character's signature.
    "Fur pattern, IDENTICAL in every image and never mirrored: the body is "
    "mostly white. On the head, the patch around the eye on the VIEWER'S LEFT "
    "side (and the forehead above it) is DARK ORANGE, and the patch covering "
    "the ear and cheek on the VIEWER'S RIGHT side is BLACK. On the lower body, "
    "a large DARK ORANGE patch covers the flank and hind leg on the VIEWER'S "
    "RIGHT side, and a BLACK patch covers the flank on the VIEWER'S LEFT side. "
    "The tail is SHORT, THICK and blunt — a stub roughly as long as one of its "
    "own legs and as thick as its head is wide — white with two black bands near "
    "the tip, hanging close against the body. It must never be long, thin, "
    "curled, raised high, or ringed like a raccoon's. "
    "Front paws are white. "
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


def render_sheet(name: str, frames: list[str], subject: str, out_dir: Path) -> Path:
    out = out_dir / f"{name}.png"
    if out.exists() and out.stat().st_size > 0:
        print(f"  = {name} (cached)")
        return out
    prompt = sheet_prompt(frames, subject=subject)
    (out_dir / f"{name}.prompt.txt").write_text(prompt, encoding="utf-8")
    print(f"  > {name} ...", flush=True)
    started = time.time()
    data = generate_image(prompt, model=MODEL, out=out)
    # Some backends answer with JPEG bytes regardless of the extension we asked
    # for; sniff the magic and rename so downstream tooling never has to guess.
    if data[:2] == b"\xff\xd8":
        jpg = out.with_suffix(".jpg")
        jpg.write_bytes(data)
        out.unlink(missing_ok=True)
        out = jpg
    print(f"    {out.stat().st_size / 1024:.0f} KiB in {time.time() - started:.1f}s")
    return out


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else "sheet"

    if mode == "sheet":
        out_dir = WORK / "views"
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, pose in SHEET_VIEWS.items():
            subject = BEAST if name.startswith("beast") else CHAR
            render_sheet(name, [pose, pose, pose, pose], subject, out_dir)
        return

    if mode == "actions":
        wanted = sys.argv[2:] or list(ACTIONS)
        out_dir = WORK / "sheets"
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest = {}
        for name in wanted:
            spec = ACTIONS[name]
            render_sheet(name, spec["frames"], spec.get("subject", CHAR), out_dir)
            manifest[name] = spec["frames"]
        (WORK / "actions.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    raise SystemExit(f"unknown mode: {mode}")


if __name__ == "__main__":
    main()
