#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Render the same character description with several image models.

Picking the art style is the one decision that is worth doing by eye, so this
script produces a side-by-side shortlist instead of guessing. Output lands in
``work/candidates/`` with the model id in the file name.

Model ids are backend-specific, so the list adapts: Gemini image models are
referred to by their bare name on Google AI Studio and by their vendor-prefixed
name on every OpenAI-compatible relay.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gen_art  # noqa: E402
from imggen import generate as generate_image, pick  # noqa: E402

# Bare names as Google AI Studio spells them; the relay spelling is derived.
MODELS_BARE = [
    "gemini-3-pro-image",
    "gemini-3.1-flash-image",
    "gemini-3.1-flash-lite-image",
    "gemini-2.5-flash-image",
]


def models_for(backend_id: str) -> list[str]:
    """Model ids for the active backend, prefixed where the relay expects it."""
    if backend_id == "google":
        return list(MODELS_BARE)
    prefixed = [f"google/{name}" for name in MODELS_BARE]
    # The relay carries non-Google image models too; they are worth a look when
    # the shortlist is being redone, but they are not the default comparison.
    return prefixed + ["microsoft/mai-image-2.5-pro", "openai/gpt-image-2"]


def main() -> None:
    out_dir = gen_art.ROOT / "work" / "candidates"
    out_dir.mkdir(parents=True, exist_ok=True)
    pose = gen_art.SHEET_VIEWS["front"]
    prompt = gen_art.sheet_prompt([pose] * 4)
    (out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    active = pick()
    print(f"backend: {active.label}\n")
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    for model in models_for(active.id):
        if only and not any(o in model for o in only):
            continue
        # The extension is decided by the returned bytes, so the cache check
        # covers every format a backend might answer with.
        existing = next((p for p in out_dir.glob(f"front-{model.replace('/', '__')}.*")
                         if p.suffix in (".png", ".jpg", ".webp")), None)
        if existing is not None and existing.stat().st_size > 0:
            print(f"= {model} (cached)")
            continue
        print(f"> {model}", flush=True)
        try:
            data = generate_image(prompt, model=model, retries=2)
            out = out_dir / f"front-{model.replace('/', '__')}{gen_art._extension_for(data)}"
            out.write_bytes(data)
            print(f"  ok {out.stat().st_size / 1024:.0f} KiB")
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"  FAIL {type(exc).__name__}: {str(exc)[:220]}")


if __name__ == "__main__":
    main()
