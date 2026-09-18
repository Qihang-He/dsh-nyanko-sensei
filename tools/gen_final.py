#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate the character sheet with the wording that actually works.

This file exists because the working prompt was not the one this project spent
nine generations arriving at. It was one sentence, and comparing the two is the
whole lesson:

    WORKS   "生成一张高还原度的娘口三三色图：保留斑 / 娘口三三的肥胖猫咪体型、
             白花纹、表情与日式妖怪气质，采用干净动漫角色立绘构图。
             先锁定角色外观参考，再直接出图。"

    FAILED  "娘口三三，日本动画《夏目友人帐》里的猫，全身正面站姿，日式动画
             赛璐璐上色风格，清晰描边，纯色品红背景（#FF00FF）铺满整个画面，
             没有阴影、没有地面、没有倒影。作为 2D 游戏精灵图使用：角色居中，
             全身完整落在画面内……"

The working version is *shorter* and it is shorter in a specific way: it names
the traits that describe **bearing and style** — 肥胖猫咪体型 (fat cat build),
表情 (expression), 日式妖怪气质 (Japanese yokai bearing) — and names one
composition target, 干净动漫角色立绘构图 (clean anime character illustration
sheet framing). It says nothing about where the patches go, what colour the
outline is, or what the background should be.

Three specific words in the failed version were actively harmful, and they are
worth naming so they are not reintroduced:

* **"游戏精灵图" (game sprite)** pushed the model toward *game character*, which
  for this styling meant anthropomorphised — one result was a child in a cat
  costume, another a cat in a business suit.
* **"四脚着地站姿" (standing on all four legs)** fought the prior. Chinese has no
  tense, and 站着 reads as "standing upright, like a person"; the model drew a
  biped.
* **A full marking description** competed with the model's own knowledge and lost
  in the wrong places — most memorably by turning "two patches separated by a
  narrow white seam" into a bold white stripe down the face.

So this asks for the character, its bearing, and the framing style, and then
stops. The background is whatever the model chooses; the matte handles it, and a
flat studio background is what 立绘 framing produces anyway.

Usage:
    python gen_final.py                    # 4 attempts, keep the good ones
    python gen_final.py --n 6
    python gen_final.py --pose 坐姿
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from PIL import Image, ImageDraw  # noqa: E402
from platform import Budget, DEFAULT_IMAGE_MODEL, generate_image, image_size  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "work" / "final"

# The template that produced a usable result first time. `pose` defaults to the
# wording that worked; other postures are appended the same terse way.
BASE = ("生成一张高还原度的{name}立绘：保留它的{traits}，"
        "采用干净动漫角色立绘构图，先锁定角色外观参考，再直接出图。")

TRAITS = {
    "站立": "肥胖猫咪体型、三花白花纹、表情与日式妖怪气质、全身站姿",
    "坐姿": "肥胖猫咪体型、三花白花纹、表情与日式妖怪气质、端坐姿势",
    "趴着": "肥胖猫咪体型、三花白花纹、表情与日式妖怪气质、趴卧姿势",
    "睡觉": "肥胖猫咪体型、三花白花纹、日式妖怪气质、蜷缩睡觉的姿势",
}

NAMES = "娘口三三"


def build_prompt(pose: str, name: str = NAMES) -> str:
    return BASE.format(name=name, traits=TRAITS[pose])


def main() -> None:
    argv = sys.argv[1:]
    pose = argv[argv.index("--pose") + 1] if "--pose" in argv else "站立"
    n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 4
    if pose not in TRAITS:
        raise SystemExit(f"unknown pose {pose!r}; pick from {list(TRAITS)}")

    prompt = build_prompt(pose)
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"prompt ({len(prompt)} chars): {prompt}")
    print(f"attempts: {n}   (~CNY {0.20 * n:.2f})   output: {OUT}\n")

    budget = Budget(6.0, dry_run="--dry-run" in argv, label=f"final {pose}")
    written: list[Path] = []
    for index in range(n):
        try:
            images = generate_image(prompt, model=DEFAULT_IMAGE_MODEL,
                                    size=image_size(1024, 1024), images=1,
                                    budget=budget)
        except Exception as exc:  # noqa: BLE001
            print(f"  attempt {index}: FAILED {str(exc)[:140]}")
            continue
        for data in images:
            suffix = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
            path = OUT / f"{pose}-{index:02d}{suffix}"
            path.write_bytes(data)
            written.append(path)
            print(f"  attempt {index}: {path.name}  {len(data) / 1024:.0f} KiB")

    if written:
        height, gap, label = 420, 14, 22
        panels = []
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
        sheet_path = OUT / f"compare-{pose}.png"
        sheet.save(sheet_path)
        print(f"\ncompare: {sheet_path}")
    print(budget.report())


if __name__ == "__main__":
    main()
