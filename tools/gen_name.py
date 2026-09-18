#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate the character sheet by naming it, with the description cut right back.

What the experiments established, in order:

1. **Describing the character at length made it worse.** A 2900-character
   specification produced a bold white stripe down the face, long whiskers, ringed
   tail and a generic-cute face. The description was not adding information; it was
   competing with the model's own knowledge and winning in the wrong places.
2. **Conditioning on a reference image capped the quality.** The only clean
   reference available was a 180x240 crop of a compressed screenshot, and every
   artefact traced back to it — fuzzy outline, drifted proportions. It also bled
   the chroma key into the character's outline.
3. **Naming the character works — but only if almost nothing else is said.**
   With the name plus framing and background, both spellings came out right.
   Adding one clause too many broke it in a specific and instructive way:
   "作为 2D 游戏精灵图" (as a 2D game sprite) made the model draw a *game
   character*, which for the nickname spelling meant a small girl in a tiger
   onesie. "四脚着地站立" (standing on all four legs) also fought the prior:
   Chinese has no tense, and 站着 reads as "standing upright, like a person".

The rule this file now follows: say the name, say the pose in the fewest words
that name a posture, say the medium and the background, and stop. Every extra
clause has to argue with a prior that is better informed than the clause is.

Note the spelling matters — 娘口三三 is the fan nickname and carries the
strongest prior; a wrong reading of it produced the onesie.

Usage:
    python gen_name.py                      # default names, standing sprite
    python gen_name.py --pose lying
    python gen_name.py --names 娘口三三 --views 2
    python gen_name.py --bg white           # for a design sheet, not for keying
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from PIL import Image, ImageDraw  # noqa: E402
from platform import Budget, DEFAULT_IMAGE_MODEL, generate_image, image_size  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "work" / "named"

# The spelling matters: the Chinese fan nickname carries the strongest prior.
NAMES = ["娘口三三", "猫咪老师", "ニャンコ先生"]

# Named postures only, no elaboration. "四脚着地" and "游戏精灵图" were both
# removed after they demonstrably steered the model wrong.
FRAMING = {
    "front": "全身，面朝镜头",
    "sitting": "全身坐姿，面朝镜头",
    "lying": "趴着，面朝镜头",
    "sleeping": "蜷成一团睡觉，闭着眼睛",
    "side": "全身侧面",
}

MEDIUM = "日本动画赛璐璐上色风格，干净描边"

BACKGROUNDS = {
    "magenta": "纯品红背景铺满画面，无阴影",
    "green": "纯绿背景铺满画面，无阴影",
    "blue": "纯蓝背景铺满画面，无阴影",
    "white": "纯白背景，无阴影",
}


def build_prompt(name: str, pose: str, background: str) -> str:
    """Name, posture, medium, background. Nothing else — see the module docstring."""
    return f"{name}，{FRAMING[pose]}。{MEDIUM}。{background}。"


def review(png: bytes, dest: Path) -> None:
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    for label, colour in (("panel", (128, 128, 132, 255)),):
        panel = Image.new("RGBA", image.size, colour)
        panel.alpha_composite(image)
        panel.convert("RGB").save(dest.with_name(f"{dest.stem}-{label}.png"))


def main() -> None:
    argv = sys.argv[1:]
    names = [argv[argv.index("--names") + 1]] if "--names" in argv else NAMES
    pose = argv[argv.index("--pose") + 1] if "--pose" in argv else "front"
    bg = argv[argv.index("--bg") + 1] if "--bg" in argv else "magenta"
    views = int(argv[argv.index("--views") + 1]) if "--views" in argv else 1
    if pose not in FRAMING:
        raise SystemExit(f"unknown pose {pose!r}; pick from {list(FRAMING)}")
    if bg not in BACKGROUNDS:
        raise SystemExit(f"unknown background {bg!r}; pick from {list(BACKGROUNDS)}")

    OUT.mkdir(parents=True, exist_ok=True)
    budget = Budget(6.0, dry_run="--dry-run" in argv, label="named")
    written: list[tuple[str, Path]] = []

    for name in names:
        prompt = build_prompt(name, pose, BACKGROUNDS[bg])
        print(f"\n=== {name}  ({len(prompt)} chars)")
        print(f"  {prompt}")
        try:
            images = generate_image(prompt, model=DEFAULT_IMAGE_MODEL,
                                    size=image_size(1024, 1024), images=views,
                                    budget=budget)
        except Exception as exc:  # noqa: BLE001 - a refusal is a result
            print(f"  FAILED: {str(exc)[:220]}")
            continue
        for index, data in enumerate(images):
            suffix = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
            path = OUT / f"{pose}-{name}-{index:02d}{suffix}"
            path.write_bytes(data)
            (OUT / f"{pose}-{name}-{index:02d}.prompt.txt").write_text(prompt, encoding="utf-8")
            review(data, OUT / f"{pose}-{name}-{index:02d}")
            written.append((name, path))
            print(f"  {path.name}  {len(data) / 1024:.0f} KiB")

    if len(written) > 1:
        height, gap, label = 440, 16, 26
        panels = []
        for name, path in written:
            image = Image.open(path).convert("RGBA")
            factor = height / image.height
            image = image.resize((max(1, int(image.width * factor)), height), Image.LANCZOS)
            panel = Image.new("RGBA", image.size, (255, 255, 255, 255))
            panel.alpha_composite(image)
            panels.append((name, panel.convert("RGB")))
        width = sum(p.width for _, p in panels) + gap * (len(panels) + 1)
        sheet = Image.new("RGB", (width, height + label + gap * 2), (24, 24, 28))
        draw = ImageDraw.Draw(sheet)
        x = gap
        for name, panel in panels:
            sheet.paste(panel, (x, gap))
            draw.text((x, gap + height + 6), name, fill=(226, 226, 234))
            x += panel.width + gap
        sheet.save(OUT / f"compare-{pose}.png")
        print(f"\ncompare: {OUT / f'compare-{pose}.png'}")

    print(budget.report())


if __name__ == "__main__":
    main()
