#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate by naming the character, and compare against describing it.

The insight this tests is the one that should have come first: a text-to-image
model trained on a large Chinese corpus already has a strong prior for a
well-known anime character. Writing 2900 characters of feature description does
not add to that prior — it competes with it, and wins in the wrong places. The
observed failure is a good example: asked for "two patches separated by a narrow
white gap", the model drew a bold white stripe down the face, because the
instruction was louder than the prior.

So this asks by name, with a minimal style and framing clause, and nothing else.
Two spellings are tried because the prior may be stronger for one than another:

  娘口三三   — the Chinese fan nickname, literally a transliteration
  猫咪老师   — the Chinese official-ish name, "Teacher Cat"

A refusal or an unrelated subject is a real possible outcome: named-character
reproduction is a thing engines sometimes decline, and that has to be measured
rather than assumed in either direction.

Usage:
    python gen_byname.py                       # both names, magenta background
    python gen_byname.py --names 娘口三三
    python gen_byname.py --views 2             # two variants per name
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from PIL import Image, ImageDraw  # noqa: E402
from platform import Budget, DEFAULT_IMAGE_MODEL, generate_image, image_size  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "work" / "byname"

NAMES = ["娘口三三", "猫咪老师"]

# Deliberately minimal. The only things the prior cannot supply are the framing
# and the background, so those are all this asks for. Anything more starts
# arguing with the model about what the character looks like.
TEMPLATE = (
    "{name}，日本动画《夏目友人帐》里的猫，全身正面站姿，"
    "日式动画赛璐璐上色风格，清晰描边，"
    "纯色品红背景（#FF00FF）铺满整个画面，没有阴影、没有地面、没有倒影。"
)


def review(png: bytes, dest: Path) -> None:
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    for name, colour in (("magenta", (255, 0, 255, 255)),
                         ("grey", (128, 128, 132, 255))):
        panel = Image.new("RGBA", image.size, colour)
        panel.alpha_composite(image)
        panel.convert("RGB").save(dest.with_name(f"{dest.stem}-{name}.png"))


def main() -> None:
    argv = sys.argv[1:]
    names = NAMES
    if "--names" in argv:
        names = [argv[argv.index("--names") + 1]]
    views = int(argv[argv.index("--views") + 1]) if "--views" in argv else 1

    OUT.mkdir(parents=True, exist_ok=True)
    budget = Budget(6.0, dry_run="--dry-run" in argv, label="by-name")
    written: list[tuple[str, Path]] = []

    for name in names:
        prompt = TEMPLATE.format(name=name)
        print(f"\n=== {name}")
        print(f"  prompt: {prompt}")
        try:
            images = generate_image(prompt, model=DEFAULT_IMAGE_MODEL,
                                    size=image_size(1024, 1024), images=views,
                                    budget=budget)
        except Exception as exc:  # noqa: BLE001 - a refusal is a result, not a crash
            print(f"  FAILED: {str(exc)[:220]}")
            continue
        for index, data in enumerate(images):
            suffix = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
            path = OUT / f"{name}-{index:02d}{suffix}"
            path.write_bytes(data)
            review(data, OUT / f"{name}-{index:02d}")
            written.append((name, path))
            print(f"  {path.name}  {len(data) / 1024:.0f} KiB")

    if written:
        height = 440
        gap, label = 16, 26
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
        sheet_path = OUT / "compare.png"
        sheet.save(sheet_path)
        print(f"\ncompare: {sheet_path}")

    print(budget.report())


if __name__ == "__main__":
    main()
