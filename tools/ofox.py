#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Minimal OfoxAI relay client used by the asset pipeline.

Reads the API key from the DSH credential store so the secret is never written
to a file, a command line, or a log. Only the endpoints the pipeline needs are
implemented: image generation (Gemini image models) and chat completions.
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

import requests
import yaml

BASE = "https://api.ofox.io/v1"
CRED = Path(os.environ.get("DSH_HOME", Path.home() / ".dsh")) / ".credentials.yaml"


def api_key() -> str:
    """Return the OfoxAI key from the DSH credential store."""
    refs = (yaml.safe_load(CRED.read_text(encoding="utf-8")) or {}).get("refs", {})
    key = str(refs.get("OFOX_API_KEY", "")).strip()
    if not key:
        raise SystemExit(f"no OFOX_API_KEY in {CRED}")
    return key


def _headers() -> dict:
    return {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}


def generate_image(prompt: str, model: str = "google/gemini-3.1-flash-image",
                   out: str | Path | None = None, retries: int = 3,
                   timeout: int = 180) -> bytes:
    """Generate one image and optionally write it to ``out``. Returns PNG bytes."""
    body = {"model": model, "prompt": prompt}
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(f"{BASE}/images/generations", headers=_headers(),
                              json=body, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - network flake is retryable
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(3 * attempt)
            continue
        if r.status_code == 200:
            payload = r.json()
            items = payload.get("data") or []
            if not items:
                last = f"empty data: {json.dumps(payload)[:200]}"
                time.sleep(3 * attempt)
                continue
            item = items[0]
            raw = item.get("b64_json")
            if raw:
                data = base64.b64decode(raw)
            elif item.get("url"):
                data = requests.get(item["url"], timeout=timeout).content
            else:
                last = f"no b64_json/url: {json.dumps(item)[:200]}"
                time.sleep(3 * attempt)
                continue
            if out is not None:
                p = Path(out)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            return data
        last = f"HTTP {r.status_code}: {r.text[:300]}"
        # 402 (credits) and 400 (bad payload) are not worth retrying.
        if r.status_code in (400, 401, 402, 403):
            break
        time.sleep(3 * attempt)
    raise RuntimeError(f"image generation failed ({model}): {last}")


def chat(messages: list[dict], model: str = "google/gemini-3.1-flash",
         max_tokens: int = 2048, timeout: int = 180) -> str:
    """One non-streaming chat completion; returns the assistant text."""
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    r = requests.post(f"{BASE}/chat/completions", headers=_headers(), json=body,
                      timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"chat failed HTTP {r.status_code}: {r.text[:300]}")
    return (r.json()["choices"][0]["message"].get("content") or "").strip()


def chat_with_images(prompt: str, images: list[bytes], model: str = "google/gemini-3.1-flash-image",
                     timeout: int = 240) -> tuple[str, list[bytes]]:
    """Multimodal edit: send reference images plus a prompt.

    Returns ``(text, images_out)`` where ``images_out`` are any images the model
    returned inline. Kept here so image-to-image editing has one entry point.
    """
    content: list[dict] = [{"type": "text", "text": prompt}]
    for blob in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64," + base64.b64encode(blob).decode()},
        })
    body = {"model": model, "messages": [{"role": "user", "content": content}]}
    r = requests.post(f"{BASE}/chat/completions", headers=_headers(), json=body,
                      timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"chat_with_images failed HTTP {r.status_code}: {r.text[:400]}")
    msg = r.json()["choices"][0]["message"]
    text = (msg.get("content") or "").strip() if isinstance(msg.get("content"), str) else ""
    out: list[bytes] = []
    for part in msg.get("images") or []:
        url = (part.get("image_url") or {}).get("url") if isinstance(part, dict) else None
        if url and url.startswith("data:") and "," in url:
            out.append(base64.b64decode(url.split(",", 1)[1]))
    return text, out


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "img":
        generate_image(sys.argv[2], out=sys.argv[3] if len(sys.argv) > 3 else None)
        print("ok")
    else:
        print(chat([{"role": "user", "content": "Reply with exactly: OK"}],
                   model="openai/gpt-5-nano", max_tokens=16))
