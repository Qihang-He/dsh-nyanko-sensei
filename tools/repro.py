#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Reproduce the one generation that came out right, and measure the hit rate.

Eight generations were spent learning that this is not a prompt-engineering
problem with a stable solution. The tally:

  * 1 succeeded — the very first by-name attempt, 75 characters.
  * 7 drifted, in ways that were not small: a girl in a tiger onesie walking a
    dog, a black-and-white tuxedo cat, a cat in a business suit and glasses, a
    tiger-striped tabby, a small girl in tiger pyjamas. Same character, same
    language, largely the same words.

That pattern — mostly wrong with an occasional hit, and no correlation between
prompt quality and outcome — is what sampling variance looks like when a model's
prior for a subject is weak or contested. It is worth stating plainly because it
changes the plan: the right move is not to keep tuning the prompt, it is to
generate several and keep the good ones, and to budget for the hit rate.

This script does that: it re-runs the exact prompt that worked, several times,
and reports how many were usable. It writes every result with an index so a good
one cannot be overwritten by the next attempt.

Usage:
    python repro.py                 # 4 attempts with the known-good prompt
    python repro.py --n 6
    python repro.py --tag alt       # write into a separate folder
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from PIL import Image, ImageDraw  # noqa: E402
from platform import Budget, DEFAULT_IMAGE_MODEL, generate_image, image_size  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "work" / "repro"

# The exact wording of the single successful generation. Not improved, not
# corrected — reproduced, so the hit rate is measured against a fixed point.
GOOD_PROMPT = (
    "娘口三三，日本动画《夏目友人帐》里的猫，全身正面站姿，"
    "日式动画赛璐璐上色风格，清晰描边，"
    "纯色品红背景（#FF00FF）铺满整个画面，没有阴影、没有地面、没有倒影。"
)


def main() -> None:
    argv = sys.argv[1:]
    n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 4
    tag = argv[argv.index("--tag") + 1] if "--tag" in argv else "repro"
    out = ROOT / "work" / tag
    out.mkdir(parents=True, exist_ok=True)

    print(f"prompt ({len(GOOD_PROMPT)} chars): {GOOD_PROMPT}")
    print(f"attempts: {n}   output: {out}")
    print()

    budget = Budget(6.0, dry_run="--dry-run" in argv, label=tag)
    written: list[Path] = []
    failures = 0
    for index in range(n):
        try:
            images = generate_image(GOOD_PROMPT, model=DEFAULT_IMAGE_MODEL,
                                    size=image_size(1024, 1024), images=1,
                                    budget=budget)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  attempt {index}: FAILED {str(exc)[:140]}")
            continue
        for data in images:
            suffix = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
            path = out / f"{tag}-{index:02d}{suffix}"
            path.write_bytes(data)
            written.append(path)
            print(f"  attempt {index}: {path.name}  {len(data) / 1024:.0f} KiB")

    if written:
        height, gap, label = 400, 14, 22
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
        sheet_path = out / f"compare-{tag}.png"
        sheet.save(sheet_path)
        print(f"\ncompare: {sheet_path}")

    print(f"\n{len(written)} image(s) written, {failures} call(s) failed")
    print(budget.report())
    print("\nNow LOOK at them: the whole point is that only some will be right, so")
    print("picking is a human judgement, not a metric.")


if __name__ == "__main__":
    main()
