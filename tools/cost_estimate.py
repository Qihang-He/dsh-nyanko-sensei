#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Estimate the asset-build cost before any credit is bought.

Buying API credit is the one step in this project that spends real money, so the
arithmetic lives in a file that can be re-run and edited rather than in someone's
head. Prices are **inputs, not constants** — verify them on the provider's rate
card and update them here.

Rate references (checked 2026-09, Volcengine Ark):
  * Seedance video: about CNY 1.00 per second of output for the standard model;
    the mini variant is quoted at roughly half that.
  * Seedream image: about CNY 0.20 per image.

The point of this script is the *staged* plan at the bottom. Spending is ordered
so that the cheapest step proves the whole pipeline before the expensive step is
funded, because the failure mode that wastes money here is buying video credit
and only then discovering the character does not look right.
"""
from __future__ import annotations

# Distinct animations the pet ships (see ANIMS in lib/client.js).
ACTIONS = 13

# Image calls actually needed. The reference sheet is produced once and reused
# as the conditioning input for every action, so it is one call plus one per
# action — an earlier revision of this estimate charged for six separate
# reference views, which nothing in the pipeline requires.
IMAGE_CALLS = 1 + ACTIONS
IMAGE_RETRY_ALLOWANCE = 4
IMAGE_PRICE = 0.20                       # CNY per image

# Video seconds per action. Most of these actions are 0.5–1 s of real motion looped
# three or four times; only the walk and the reactions need a longer take.
VIDEO_SECONDS = {
    "short (simple loops)": 2,
    "standard": 5,
}
VIDEO_PRICES = {                         # CNY per second of output
    "Seedance 2.0": 1.00,
    "Seedance 2.0 mini": 0.50,
}


def money(value: float) -> str:
    return f"CNY {value:6.2f}"


def main() -> None:
    images = (IMAGE_CALLS + IMAGE_RETRY_ALLOWANCE) * IMAGE_PRICE

    print("=== Images only (Path B: pose sheets -> transparent webm) ===")
    print(f"  {IMAGE_CALLS} calls + {IMAGE_RETRY_ALLOWANCE} retries at "
          f"CNY {IMAGE_PRICE:.2f} = {money(images)}")
    print("  No video credit. Motion is a puppet: one pose per action,")
    print("  deformed programmatically. This is the step to do FIRST.")
    print()

    print("=== Images + video (Path A: green-screen clip -> matte -> transparent webm) ===")
    print("  Real articulation: limbs move, expressions change.")
    for label, seconds in VIDEO_SECONDS.items():
        for name, price in VIDEO_PRICES.items():
            video = ACTIONS * seconds * price
            print(f"  {name:18s} {label:24s} {ACTIONS} x {seconds}s x "
                  f"CNY {price:.2f}/s = {money(video)}   "
                  f"total {money(video + images)}")
    print()

    print("=== Staged plan (spend in this order) ===")
    print(f"  Step 1  top up CNY 10")
    print(f"          run the image stage only            spend about {money(images)}")
    print(f"          LOOK at the result before continuing.")
    print(f"  Step 2  if the character looks right, top up CNY 30–50")
    print(f"          run the video stage with mini, 2 s   spend about "
          f"{money(ACTIONS * 2 * 0.50)}")
    print(f"  Step 3  re-run only the actions that need a longer take")
    print()
    print("  Do NOT fund both stages up front. If the character is wrong, the")
    print("  video credit is wasted — and fixing the character is an image-stage")
    print("  problem, which is a tenth of the cost.")


if __name__ == "__main__":
    main()
