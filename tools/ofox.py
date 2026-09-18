#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""OfoxAI relay helpers.

Image generation moved to :mod:`imggen`, which picks a backend from whichever
credential is configured instead of hard-depending on this one relay. The name
``generate_image`` is kept as a thin alias so the art pipeline keeps working and
so an existing OfoxAI-only setup needs no change at all.

What stays here is the relay-specific chat client the *critique* step uses: the
vision model that reads a generated sprite sheet back and reports how far it is
from the reference.

Secrets are read from the DSH credential store (or the environment) and are
never written to a file, a command line, or a log.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

import requests
import yaml

# Re-exported so callers can keep importing generation from one place.
from imggen import generate as generate_image  # noqa: F401,E402

BASE = "https://api.ofox.io/v1"
CRED = Path(os.environ.get("DSH_HOME", Path.home() / ".dsh")) / ".credentials.yaml"


def api_key() -> str:
    """Return the OfoxAI key, preferring the environment over the store."""
    key = os.environ.get("OFOX_API_KEY")
    if key and key.strip():
        return key.strip()
    refs = (yaml.safe_load(CRED.read_text(encoding="utf-8")) or {}).get("refs", {})
    key = str(refs.get("OFOX_API_KEY", "")).strip()
    if not key:
        raise SystemExit(f"no OFOX_API_KEY in the environment or in {CRED}")
    return key


def _headers() -> dict:
    return {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}


def chat(messages: list[dict], model: str = "google/gemini-3.1-flash",
         max_tokens: int = 2048, timeout: int = 180) -> str:
    """One non-streaming chat completion; returns the assistant text."""
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    r = requests.post(f"{BASE}/chat/completions", headers=_headers(), json=body,
                      timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"chat failed HTTP {r.status_code}: {r.text[:300]}")
    return (r.json()["choices"][0]["message"].get("content") or "").strip()


def describe_image(image: bytes | Path | str, question: str,
                   model: str = "google/gemini-3.1-flash",
                   max_tokens: int = 900, timeout: int = 240) -> str:
    """Ask a vision model about an image — the critique half of the art loop.

    The art pipeline generates from a written description, and a written
    description is exactly the kind of thing that silently drifts from the
    reference. This is how the drift gets caught: the rendered result is shown
    back to a vision model and compared against the calibration notes.
    """
    if isinstance(image, (str, Path)):
        image = Path(image).read_bytes()
    url = "data:image/png;base64," + base64.b64encode(image).decode()
    return chat([{
        "role": "user",
        "content": [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": url}},
        ],
    }], model=model, max_tokens=max_tokens, timeout=timeout)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "img":
        prompt = sys.argv[2] if len(sys.argv) > 2 else "a small red circle on white"
        out = sys.argv[3] if len(sys.argv) > 3 else None
        generate_image(prompt, out=out)
        print("ok")
    else:
        print(chat([{"role": "user", "content": "Reply with exactly: OK"}],
                   model="openai/gpt-5-nano", max_tokens=16))
