#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Where to spend a CNY 20 budget for the best likeness per yuan.

Two facts drive the plan, and neither is obvious from a price list:

1. **Image quality does not scale with spend.** Seedream charges a flat rate per
   image, so money buys *attempts*, not fidelity. What buys fidelity is
   conditioning on a reference image — passing the approved character sheet as
   the ``image`` input — which is implemented in `platform.py` and costs the same
   as a text-only call. A tight budget therefore costs retries, not likeness.

2. **Video is where the budget goes, and it is not needed everywhere.** Real
   articulation matters most where limbs move: walking and the reactions. An
   idle loop, a blink, a breath or an ear flick is a whole-body transform that
   procedural deformation already does convincingly, because there are no
   independent limbs to get wrong.

So the allocation is per action, by how much articulation that action actually
needs — not spread evenly, and not spent on video for motion the deformation
path already handles.

Run this before topping up: `python tools/spend_plan.py`.
"""
from __future__ import annotations

BUDGET = 20.0            # CNY
IMAGE_PRICE = 0.20       # CNY per image
VIDEO_MINI = 0.50        # CNY per second, seedance-2.0-mini
VIDEO_FULL = 1.00        # CNY per second, seedance-2.0

# Every action, with the articulation it needs.
#   "video"    - limbs must move; deformation cannot fake it
#   "deform"   - a whole-body transform; the free path already looks right
#   "both"     - video adds something, but the action works without it
ACTIONS: dict[str, str] = {
    "idle": "deform",
    "breathe_deep": "deform",
    "look_around": "deform",
    "sleep": "deform",
    "ear_flick": "deform",
    "spin": "deform",
    "bounce_land": "deform",
    "drag": "deform",
    "walk": "video",
    "hop": "video",
    "happy": "video",
    "angry": "video",
    "surprised": "both",
}

# Image work: one character sheet, one pose sheet per action, plus retries for the
# sheet (the only image that has to be right).
CHARACTER_SHEETS = 1
RETRY_ON_SHEET = 8


def money(value: float) -> str:
    return f"CNY {value:5.2f}"


def main() -> None:
    video_actions = [a for a, k in ACTIONS.items() if k == "video"]
    both_actions = [a for a, k in ACTIONS.items() if k == "both"]
    deform_actions = [a for a, k in ACTIONS.items() if k == "deform"]

    print("=== Step 1: the character sheet. Spend here first. ===")
    sheet_calls = CHARACTER_SHEETS + RETRY_ON_SHEET
    sheet_cost = sheet_calls * IMAGE_PRICE
    print(f"  {sheet_calls} images x {money(IMAGE_PRICE)} = {money(sheet_cost)}")
    print("  That is up to nine attempts at ONE image, conditioned on your")
    print("  reference art. Likeness is decided here, and it is the cheap half")
    print("  of the build, so retrying until it is right costs almost nothing.")
    print()

    print("=== Step 2: pose sheets for every action. ===")
    pose_cost = len(ACTIONS) * IMAGE_PRICE
    print(f"  {len(ACTIONS)} images x {money(IMAGE_PRICE)} = {money(pose_cost)}")
    print()

    remaining = BUDGET - sheet_cost - pose_cost
    print(f"=== Step 3: video, with {money(remaining)} left of {money(BUDGET)}. ===")
    for seconds in (2, 3):
        rows = []
        need = (len(video_actions) + len(both_actions))
        mini = need * seconds * VIDEO_MINI
        rows.append(("seedance-2.0-mini", seconds, need, mini))
        full = need * seconds * VIDEO_FULL
        rows.append(("seedance-2.0", seconds, need, full))
        for name, secs, clips, cost in rows:
            verdict = "fits" if cost <= remaining else f"over by {money(cost - remaining)}"
            print(f"  {name:18s} {clips} clips x {secs}s  = {money(cost):>9s}   {verdict}")
    print()

    print("=== The plan that fits CNY 20 ===")
    mini_2 = (len(video_actions) + len(both_actions)) * 2 * VIDEO_MINI
    full_2 = (len(video_actions) + len(both_actions)) * 2 * VIDEO_FULL
    video_only = len(video_actions) * 2 * VIDEO_FULL
    print(f"  {money(sheet_cost)}  character sheet, retried until on-model")
    print(f"  {money(pose_cost)}  pose sheet for all {len(ACTIONS)} actions")
    print(f"  {money(video_only)}  {len(video_actions)} clips x 2s x full "
          f"({', '.join(video_actions)})")
    print(f"  {money(0.0)}  {len(deform_actions)} actions made by deformation, no credit")
    total = sheet_cost + pose_cost + video_only
    print(f"  {'-' * 46}")
    print(f"  {money(total)}  total, {money(BUDGET - total)} spare for retries")
    print()
    print("  With this much headroom, use the FULL Seedance model, not mini:")
    print("  the four clips cost CNY 8.00 rather than CNY 4.00, and the extra")
    print("  CNY 4.00 buys visibly better motion on exactly the actions where")
    print("  motion is the whole point.")
    if remaining >= full_2:
        print(f"  The 'both' action(s) ({', '.join(both_actions)}) fit as well: "
              f"add {money(len(both_actions) * 2 * VIDEO_FULL)}.")
    print()
    print("=== Why this is not a compromise on likeness ===")
    print("  Likeness is set by the character sheet in step 1, which gets the")
    print("  largest share of the image budget and is retried until it matches.")
    print("  The video budget is spent only where limbs actually move; the other")
    print(f"  {len(deform_actions)} actions are whole-body transforms that the free")
    print("  deformation path already renders convincingly.")


if __name__ == "__main__":
    main()
