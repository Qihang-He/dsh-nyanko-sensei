#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate the per-action pose sheets, conditioned on the approved sprite.

Why this is the next step: everything so far deforms **one** drawing, so limbs
cannot articulate — the walk cannot lift a leg, the reactions cannot change
expression. A pose sheet per action fixes that at the source: four drawn poses
per action, warped and interlaced into a loop.

The conditioning reference is the sprite the user approved, not the raw stills.
That is the whole point of approving one: it becomes the canonical appearance, and
every later generation is anchored to it rather than to a vague description.

Format follows what the rest of the pipeline already consumes: one 2x2 sheet per
action, four quadrants, read in order by build_assets.split_sheet. No new format,
no new consumer.

Autonomy note for reviewers: this generates every action it is asked for and
writes each sheet as it arrives, so a failure partway through leaves the earlier
sheets usable rather than discarding the batch.

Usage:
    python gen_actions.py                     # the priority set
    python gen_actions.py --all               # all thirteen
    python gen_actions.py sitting sleeping    # named actions
    python gen_actions.py --dry-run           # price it, send nothing
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from PIL import Image  # noqa: E402
from platform import Budget, DEFAULT_IMAGE_MODEL, generate_image, image_size  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "work" / "sprites" / "base.png"      # the approved sprite
OUT = ROOT / "work" / "sheets"

BACKGROUND = "纯品红色背景（#FF00FF）铺满整个画面，没有阴影、没有地面、没有倒影"

# Every action the pet ships, with the four quadrants of its sheet. The client's
# ANIMS table is the source of truth for which actions exist; this must stay in
# step with it.
SHEETS: dict[str, list[str]] = {
    "idle": [
        "正面站立，四脚着地，放松表情",
        "正面站立，身体微微下沉，像在呼气",
        "正面站立，身体微微上升，像在吸气",
        "正面站立，耳朵轻轻动了一下",
    ],
    "look_around": [
        "正面站立，头向左转看",
        "正面站立，头回到正中",
        "正面站立，头向右转看",
        "正面站立，头回到正中，眼睛半闭",
    ],
    "ear_flick": [
        "正面站立，耳朵竖直放松",
        "正面站立，左耳向后折了一下",
        "正面站立，两只耳朵一起抖动",
        "正面站立，耳朵回到竖直放松",
    ],
    "sleep": [
        "蜷成一团趴着睡觉，闭紧眼睛",
        "蜷成一团睡觉，身体微微起伏（吸气）",
        "蜷成一团睡觉，身体微微下沉（呼气）",
        "蜷成一团睡觉，尾巴尖轻轻动了一下",
    ],
    "walk": [
        "正面视角走路，左前爪抬离地面",
        "正面视角走路，四脚都落地，身体略压低",
        "正面视角走路，右前爪抬离地面",
        "正面视角走路，四脚都落地，身体略压低",
    ],
    "hop": [
        "正面站立，四脚着地，准备起跳（微蹲）",
        "正面腾空跳起，四脚离地，身体被拉长",
        "正面落地，身体被压扁变宽",
        "正面站立，恢复原状",
    ],
    "bounce_land": [
        "正面落地瞬间，身体压得很扁很宽",
        "正面回弹，身体被拉高",
        "正面再次轻微压扁",
        "正面站立，恢复原状",
    ],
    "happy": [
        "正面站立，两只耳朵高高竖起，眼睛弯成笑",
        "正面轻轻跳起，四脚离地，耳朵竖起",
        "正面落地，身体压扁，尾巴翘起",
        "正面站立，开心地伸了个懒腰",
    ],
    "angry": [
        "正面站立，耳朵向后压平，眼睛瞪起来",
        "正面站立，一只前爪抬起像要挥打，张嘴露出小尖牙",
        "正面站立，全身炸毛变圆，尾巴竖起",
        "正面站立，恢复平静但仍瞪着眼",
    ],
    "surprised": [
        "正面站立，耳朵猛地竖直，眼睛睁大，身体僵住",
        "正面四脚离地弹起，四肢张开",
        "正面落地，身体压扁，眼睛睁大，嘴张成小圆",
        "正面站立，耳朵慢慢放松，眼睛仍睁大",
    ],
    "spin": [
        "正面站立",
        "正面站立，身体转向左侧四分之三",
        "背对镜头站立",
        "正面站立，身体转向右侧四分之三",
    ],
    "drag": [
        "被拎起悬空，四条腿无力下垂，眼睛惊讶",
        "被拎起悬空，身体向左倾，耳朵向后吹",
        "被拎起悬空，身体向右倾，尾巴向上甩",
        "被拎起悬空，扭动挣扎，表情很不耐烦",
    ],
    "breathe_deep": [
        "正面站立，身体正常",
        "正面站立，深吸气，胸腹鼓起",
        "正面站立，呼气，身体略缩",
        "正面站立，恢复原状",
    ],
}

# Actions whose motion the deformation path genuinely cannot fake, so they are
# worth generating first: visible leg articulation and expression change.
PRIORITY = ["sitting_placeholder"] if False else ["walk", "hop", "happy", "angry"]

TEMPLATE = (
    "生成一张 2x2 四格分镜图，四格画的是同一只娘口三三，"
    "日本动画赛璐璐上色风格、干净描边，构图和比例完全一致，"
    "每格只画一只猫、全身完整、居中。{background}。"
    "参考图是这只猫的标准外观，请严格保持一致（肥胖体型、三花白花纹、"
    "额头橘斑与灰斑、红棕色项圈与金色铃铛）。"
    "四格依次为：第一格{first}；第二格{second}；第三格{third}；第四格{fourth}。"
)


def flatten_on_white(path: Path) -> bytes:
    image = Image.open(path).convert("RGBA")
    canvas = Image.new("RGBA", image.size, (255, 255, 255, 255))
    canvas.alpha_composite(image)
    buffer = io.BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def prompt_for(action: str) -> str:
    cells = SHEETS[action]
    return TEMPLATE.format(
        background=BACKGROUND,
        first=cells[0], second=cells[1], third=cells[2], fourth=cells[3])


def main() -> None:
    argv = sys.argv[1:]
    if "--all" in argv:
        wanted = list(SHEETS)
    else:
        named = [a for a in argv if not a.startswith("--") and a in SHEETS]
        wanted = named or PRIORITY

    unknown = [a for a in argv if not a.startswith("--") and a not in SHEETS]
    if unknown:
        print(f"ignoring unknown action(s): {', '.join(unknown)}")
    if not REF.exists():
        raise SystemExit(f"no approved sprite at {REF}; run tools/adopt.py first")

    reference = flatten_on_white(REF)
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"reference: {REF.name}")
    print(f"actions:   {', '.join(wanted)}  ({len(wanted)} sheet(s), "
          f"~CNY {0.20 * len(wanted):.2f})\n")

    budget = Budget(8.0, dry_run="--dry-run" in argv, label="pose sheets")
    done: list[str] = []
    for action in wanted:
        prompt = prompt_for(action)
        (OUT / f"{action}.prompt.txt").write_text(prompt, encoding="utf-8")
        try:
            images = generate_image(prompt, model=DEFAULT_IMAGE_MODEL,
                                    references=[reference],
                                    size=image_size(1024, 1024), images=1,
                                    budget=budget)
        except Exception as exc:  # noqa: BLE001 - one bad action must not kill the run
            print(f"  {action:14s} FAILED  {str(exc)[:120]}")
            continue
        if not images:
            print(f"  {action:14s} no image returned")
            continue
        data = images[0]
        suffix = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
        path = OUT / f"{action}{suffix}"
        path.write_bytes(data)
        done.append(action)
        print(f"  {action:14s} {path.name}  {len(data) / 1024:.0f} KiB")

    print(f"\n{len(done)}/{len(wanted)} sheet(s) written to {OUT}")
    print(budget.report())
    if done:
        print("\nNext: python tools/build_assets.py frames   (splits the sheets)")
        print("      python tools/build_assets.py encode   (writes the webm)")


if __name__ == "__main__":
    main()
