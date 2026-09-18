#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Reproduce the winning flow: the user's wording, plus the reference image.

The user's own Doubao session produced a good result from a short prompt that
ended with "先锁定角色外观参考，再直接出图" — and a reference image was visible
in that session. Trying the same wording *without* a reference produced four
generic chubby calico cats: round golden eyes, no forehead marking, no collar.

That is the diagnosis: "先锁定角色外观参考" only works if there is something to
lock on to. With no image and a name whose prior the model will not honour, the
wording is a no-op and the model falls back to "generic calico".

So this supplies the reference art the earlier attempt had, and keeps the
wording short.

Background is magenta rather than green, because a green screen bled into the
character's outline on the first attempt. Magenta appears nowhere in this
character, so any contamination is obvious rather than invisible.

Usage:
    python gen_win.py                   # 2 attempts
    python gen_win.py --n 4
    python gen_win.py --bg white
    python gen_win.py --ref head        # head still only
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from PIL import Image, ImageDraw  # noqa: E402
from platform import Budget, DEFAULT_IMAGE_MODEL, generate_image, image_size  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "work" / "win"

REFS = {
    "body": ROOT / "work" / "extracted" / "OIP-C-cut.png",        # full body, clean matte
    "head": ROOT / "work" / "extracted" / "OIP-C (2)-cut.png",    # front-facing head
}

BACKGROUNDS = {
    "magenta": "纯品红色背景（#FF00FF）铺满整个画面，没有阴影、没有地面、没有倒影",
    "white": "",
    "green": "纯绿色背景铺满整个画面，没有阴影、没有地面",
}

# The user's wording, kept essentially intact. The traits describe bearing and
# style rather than marking positions — that is what made it work.
PROMPT_WITH_BG = (
    "生成一张高还原度的娘口三三立绘：保留斑、娘口三三的肥胖猫咪体型、白花纹、"
    "表情与日式妖怪气质，采用干净动漫角色立绘构图，"
    "先锁定角色外观参考，再直接出图。{background}"
)


def flatten_on_white(path: Path) -> bytes:
    image = Image.open(path).convert("RGBA")
    canvas = Image.new("RGBA", image.size, (255, 255, 255, 255))
    canvas.alpha_composite(image)
    buffer = io.BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def main() -> None:
    argv = sys.argv[1:]
    n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 2
    bg = argv[argv.index("--bg") + 1] if "--bg" in argv else "magenta"
    which = argv[argv.index("--ref") + 1] if "--ref" in argv else "both"

    if bg not in BACKGROUNDS:
        raise SystemExit(f"unknown background {bg!r}; pick from {list(BACKGROUNDS)}")

    if which == "both":
        sources = [REFS["body"], REFS["head"]]
    else:
        sources = [REFS[which]]
    references = [flatten_on_white(p) for p in sources if p.exists()]
    if not references:
        raise SystemExit(f"no reference found among {[str(p) for p in sources]}")

    prompt = PROMPT_WITH_BG.format(background=BACKGROUNDS[bg]).strip().rstrip("。") + "。"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "prompt.txt").write_text(prompt, encoding="utf-8")

    print(f"references: {[p.name for p in sources if p.exists()]}")
    print(f"prompt ({len(prompt)} chars): {prompt}")
    print(f"attempts: {n}   background: {bg}\n")

    budget = Budget(6.0, dry_run="--dry-run" in argv, label="win")
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
            path = OUT / f"win-{index:02d}{suffix}"
            path.write_bytes(data)
            written.append(path)
            print(f"  attempt {index}: {path.name}  {len(data) / 1024:.0f} KiB")

    if written:
        height, gap, label = 430, 14, 22
        panels = []
        reference_panel = Image.open(REFS["body"]).convert("RGBA")
        factor = height / reference_panel.height
        reference_panel = reference_panel.resize(
            (max(1, int(reference_panel.width * factor)), height), Image.LANCZOS)
        backdrop = Image.new("RGBA", reference_panel.size, (255, 255, 255, 255))
        backdrop.alpha_composite(reference_panel)
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
