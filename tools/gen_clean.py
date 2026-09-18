#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Refine the reference-conditioned result into a clean front-facing sprite.

Two defects survived the run that produced a usable likeness, and both are
specific enough to fix rather than re-roll blindly:

* **A mirror reflection.** The output sits on a glossy floor with the character
  mirrored below it, and the prompt's "没有倒影" did not prevent it. The cause is
  almost certainly the reference image: the extracted sprite was composited on
  white, and a plausible reading of that is "product shot on a white surface", a
  genre that conventionally includes a reflection. Fixing this means (a) asking
  again, and (b) making the pose explicit so the composition is not left open.
* **Invented limbs.** The reference is a three-quarter view with a raised paw, so
  the model inherited that stance and then improvised the rest — one result gave
  the cat an arm ending in a human-looking palm. A sprite needs a neutral
  quadruped stance: all four legs down.

So this keeps the wording that works (name plus bearing plus 立绘 framing), keeps
the reference image, and adds only two constraints that the previous run showed
were missing: a front view on all four legs, and no reflection or floor.

Cost discipline: every call is CNY 0.20 and roughly three in four land, so the
script generates several and keeps them all with an index, rather than
overwriting. Picking is a human judgement.

Usage:
    python gen_clean.py                 # 3 attempts, ~CNY 0.60
    python gen_clean.py --n 5
    python gen_clean.py --bg white
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from PIL import Image, ImageDraw  # noqa: E402
from platform import Budget, DEFAULT_IMAGE_MODEL, generate_image, image_size  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "work" / "clean"

REFS = [ROOT / "work" / "extracted" / "OIP-C-cut.png",
        ROOT / "work" / "extracted" / "OIP-C (2)-cut.png"]

# The working sentence, plus the two constraints the last run showed were missing.
# Note what is NOT here: no colour codes for the background, no marking positions,
# no style jargon. Those argued with the model's prior and lost.
PROMPT = (
    "生成一张高还原度的娘口三三立绘：保留斑、娘口三三的肥胖猫咪体型、白花纹、"
    "表情与日式妖怪气质，采用干净动漫角色立绘构图。"
    "姿态为正面视角、四条腿都着地站立的普通猫咪姿势，不要抬起前爪，"
    "不要拟人化的手臂。画面中只有这一只猫，背景干净无杂物，"
    "没有倒影、没有镜像、没有地面、没有水面。"
    "先锁定角色外观参考，再直接出图。"
)

BACKGROUNDS = {
    "magenta": "背景为纯品红色（#FF00FF）平涂。",
    "white": "",
}


def flatten_on_white(path: Path) -> bytes:
    image = Image.open(path).convert("RGBA")
    canvas = Image.new("RGBA", image.size, (255, 255, 255, 255))
    canvas.alpha_composite(image)
    buffer = io.BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def main() -> None:
    argv = sys.argv[1:]
    n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 3
    bg = argv[argv.index("--bg") + 1] if "--bg" in argv else "magenta"
    if bg not in BACKGROUNDS:
        raise SystemExit(f"unknown background {bg!r}; pick from {list(BACKGROUNDS)}")

    prompt = PROMPT + BACKGROUNDS[bg]
    references = [flatten_on_white(p) for p in REFS if p.exists()]
    if not references:
        raise SystemExit("no reference images found")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "prompt.txt").write_text(prompt, encoding="utf-8")
    print(f"references: {[p.name for p in REFS if p.exists()]}")
    print(f"prompt ({len(prompt)} chars): {prompt}")
    print(f"attempts: {n}   (~CNY {0.20 * n:.2f})\n")

    budget = Budget(8.0, dry_run="--dry-run" in argv, label="clean")
    written: list[Path] = []
    for index in range(n):
        try:
            images = generate_image(prompt, model=DEFAULT_IMAGE_MODEL,
                                    references=references,
                                    size=image_size(1024, 1024), images=1,
                                    budget=budget)
        except Exception as exc:  # noqa: BLE001
            print(f"  attempt {index}: FAILED {str(exc)[:160]}")
            continue
        for data in images:
            suffix = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
            path = OUT / f"clean-{index:02d}{suffix}"
            path.write_bytes(data)
            written.append(path)
            print(f"  attempt {index}: {path.name}  {len(data) / 1024:.0f} KiB")

    if written:
        height, gap, label = 430, 14, 22
        panels = []
        base = Image.open(REFS[0]).convert("RGBA")
        factor = height / base.height
        base = base.resize((max(1, int(base.width * factor)), height), Image.LANCZOS)
        backdrop = Image.new("RGBA", base.size, (255, 255, 255, 255))
        backdrop.alpha_composite(base)
        panels.append(("reference", backdrop.convert("RGB")))
        for path in written:
            image = Image.open(path).convert("RGBA")
            factor = height / image.height
            image = image.resize((max(1, int(image.width * factor)), height), Image.LANCZOS)
            panel = Image.new("RGBA", image.size, (255, 255, 255, 255))
            panel.alpha_composite(image)
            panels.append((path.stem, panel.convert("RGB")))
        width = sum(p.width for _, p in panels) + gap * (len(panels) + 1)
        sheet = Image.new("RGB", (width, height + label + gap * 2), (24, 24, 28))
        draw = ImageDraw.Draw(sheet)
        x = gap
        for name, panel in panels:
            sheet.paste(panel, (x, gap))
            draw.text((x, gap + height + 5), name, fill=(224, 224, 232))
            x += panel.width + gap
        sheet.save(OUT / "compare.png")
        print(f"\ncompare: {OUT / 'compare.png'}")
    print(budget.report())


if __name__ == "__main__":
    main()
