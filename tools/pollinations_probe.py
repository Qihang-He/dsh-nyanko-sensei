#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Probe what the keyless Pollinations endpoint actually honours.

The endpoint accepts a pile of query parameters and silently ignores the ones it
does not know, so guessing is worse than useless: a run can look successful while
every option was dropped. This asks for the model list, then renders one prompt
across candidate models and parameter spellings so the supported set is observed
rather than assumed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent.parent / "work" / "pollinations"
BASE = "https://image.pollinations.ai"

PROMPT = (
    "flat cel-shaded 2D anime illustration of a plump white calico cat, "
    "thick black outline, simple flat colors, on a completely flat pure green "
    "chroma-key background, no shadow, full body, centered"
)


def models() -> list[str]:
    for url in (f"{BASE}/models", "https://text.pollinations.ai/models"):
        try:
            r = requests.get(url, timeout=40)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    ids = [m.get("name") or m.get("id") or str(m) for m in data
                           if isinstance(m, (dict, str))]
                    if ids:
                        print(f"models from {url}: {len(ids)}")
                        return ids
        except Exception as exc:  # noqa: BLE001 - probing, not asserting
            print(f"  {url} -> {type(exc).__name__}: {str(exc)[:100]}")
    return []


def render(name: str, params: dict, prompt: str = PROMPT, timeout: int = 150) -> bool:
    url = f"{BASE}/prompt/{requests.utils.quote(prompt, safe='')}"
    try:
        r = requests.get(url, params=params, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        print(f"  {name:52s} ERR {type(exc).__name__}: {str(exc)[:90]}")
        return False
    ctype = r.headers.get("content-type", "")
    ok = r.status_code == 200 and ctype.startswith("image")
    detail = f"{r.status_code} {ctype} {len(r.content) / 1024:.0f} KiB"
    if ok:
        OUT.mkdir(parents=True, exist_ok=True)
        suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(ctype, ".png")
        (OUT / f"{name}{suffix}").write_bytes(r.content)
    print(f"  {name:52s} {'ok  ' if ok else 'FAIL'} {detail}")
    return ok


def main() -> None:
    found = models()
    if found:
        print("  " + ", ".join(found[:40]))
        print()

    print("parameter candidates:")
    candidates = [
        ("plain", {}),
        ("nologo", {"nologo": "true"}),
        ("seed+size", {"seed": 7, "width": 512, "height": 512}),
        ("model=flux", {"model": "flux"}),
        ("model=turbo", {"model": "turbo"}),
        ("model=kontext", {"model": "kontext"}),
        ("model=nanobanana", {"model": "nanobanana"}),
        ("model=seedream", {"model": "seedream"}),
        ("model=flux+nologo", {"model": "flux", "nologo": "true", "seed": 7}),
        ("enhance=false", {"enhance": "false", "nologo": "true", "seed": 7}),
        ("private=true", {"private": "true", "nologo": "true", "seed": 7}),
    ]
    # A short prompt keeps each probe cheap and makes style handling obvious.
    short = "flat 2D anime cel-shaded plump white calico cat, thick black outline, flat green background"
    results = {}
    for name, params in candidates:
        results[name] = render(name, params, prompt=short)
    print()
    working = [k for k, v in results.items() if v]
    print(f"{len(working)}/{len(candidates)} parameter sets accepted: {', '.join(working)}")
    print(f"images in {OUT}")


if __name__ == "__main__":
    main()
