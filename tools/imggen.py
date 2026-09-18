#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Provider-agnostic image generation.

The asset pipeline used to hard-depend on one relay. That made the whole
project hostage to one account's balance, and when that account ran dry the art
stage stopped with a 402 that had nothing to do with the code. This module is
the fix: one call site, several backends, selected by which credential is
present, so moving providers is an environment change rather than a refactor.

Backends, tried in this order:

1. **Google AI Studio** (``GEMINI_API_KEY`` / ``GOOGLE_API_KEY``) — native
   ``generateContent`` with ``responseModalities: ["IMAGE"]``. Also the cheapest
   option for this project because the free tier covers image models.
2. **OpenRouter** (``OPENROUTER_API_KEY``) — the ``/images/generations`` shape.
   This is also the only image path the harness itself registers, so it is the
   one that stays closest to what DSH supports natively.
3. **OfoxAI** (``OFOX_API_KEY``) — the original relay, kept working.

Keys are read from the environment first and then from the DSH credential store
(``$DSH_HOME/.credentials.yaml``), so nothing has to be exported twice. A key is
never logged, echoed, or written to disk.

Usage:
    python imggen.py --list
    python imggen.py out.png "a red circle on white"
"""
from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path

import requests
import yaml

DSH_HOME = Path(os.environ.get("DSH_HOME", Path.home() / ".dsh"))
CRED = DSH_HOME / ".credentials.yaml"

# Google AI Studio speaks its own protocol; everything else here is
# OpenAI-compatible enough to share a request shape.
GOOGLE_BASE = "https://generativelanguage.googleapis.com/v1beta"

DEFAULT_MODEL = {
    "google": "gemini-2.5-flash-image",
    "openrouter": "google/gemini-2.5-flash-image",
    "ofox": "google/gemini-2.5-flash-image",
}


def credential(*names: str) -> str | None:
    """First non-empty value among the environment, then the DSH store."""
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    try:
        refs = (yaml.safe_load(CRED.read_text(encoding="utf-8")) or {}).get("refs", {})
    except Exception:  # noqa: BLE001 - a missing store is simply "no key"
        return None
    for name in names:
        value = refs.get(name)
        if value and str(value).strip():
            return str(value).strip()
    return None


def sniff(data: bytes) -> str:
    """File extension for image bytes, by magic number rather than trust."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:2] == b"\xff\xd8":
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".png"


class Backend:
    """One image-generation provider."""

    id = "?"
    label = "?"

    def available(self) -> str | None:
        """Return the credential, or None when this backend is not configured."""
        raise NotImplementedError

    def generate(self, prompt: str, model: str | None = None,
                 timeout: int = 180) -> bytes:
        raise NotImplementedError


class GoogleAIStudio(Backend):
    """Google AI Studio, native REST. The free tier covers the image models."""

    id = "google"
    label = "Google AI Studio (GEMINI_API_KEY)"

    def available(self) -> str | None:
        return credential("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY")

    def generate(self, prompt: str, model: str | None = None,
                 timeout: int = 180) -> bytes:
        key = self.available()
        if not key:
            raise RuntimeError("no Google AI Studio key configured")
        model = model or DEFAULT_MODEL[self.id]
        url = f"{GOOGLE_BASE}/models/{model}:generateContent"
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        }
        r = requests.post(url, headers={
            "x-goog-api-key": key,
            "content-type": "application/json",
        }, json=body, timeout=timeout)
        if r.status_code != 200:
            raise RuntimeError(f"Google AI Studio HTTP {r.status_code}: {r.text[:400]}")
        payload = r.json()
        for candidate in payload.get("candidates", []):
            for part in (candidate.get("content") or {}).get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    return base64.b64decode(inline["data"])
        raise RuntimeError(f"Google AI Studio returned no image: {str(payload)[:400]}")


class OpenAICompatible(Backend):
    """Any ``POST {base}/images/generations`` endpoint returning b64 or a URL."""

    def __init__(self, id: str, label: str, base: str, key_names: tuple[str, ...],
                 extra_headers: dict | None = None):
        self.id = id
        self.label = label
        self.base = base.rstrip("/")
        self.key_names = key_names
        self.extra_headers = extra_headers or {}

    def available(self) -> str | None:
        return credential(*self.key_names)

    def generate(self, prompt: str, model: str | None = None,
                 timeout: int = 180) -> bytes:
        key = self.available()
        if not key:
            raise RuntimeError(f"no key configured for {self.label}")
        model = model or DEFAULT_MODEL.get(self.id, DEFAULT_MODEL["ofox"])
        r = requests.post(f"{self.base}/images/generations", headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }, json={"model": model, "prompt": prompt}, timeout=timeout)
        if r.status_code != 200:
            raise RuntimeError(f"{self.label} HTTP {r.status_code}: {r.text[:400]}")
        items = (r.json() or {}).get("data") or []
        if not items:
            raise RuntimeError(f"{self.label} returned no data: {r.text[:300]}")
        item = items[0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        if item.get("url"):
            return requests.get(item["url"], timeout=timeout).content
        raise RuntimeError(f"{self.label} returned neither b64_json nor url: {item}")


BACKENDS: list[Backend] = [
    GoogleAIStudio(),
    OpenAICompatible("openrouter", "OpenRouter (OPENROUTER_API_KEY)",
                     "https://openrouter.ai/api/v1", ("OPENROUTER_API_KEY",)),
    OpenAICompatible("ofox", "OfoxAI (OFOX_API_KEY)",
                     "https://api.ofox.io/v1", ("OFOX_API_KEY",)),
]


def pick(preferred: str | None = None) -> Backend:
    """The backend to use: the preferred one if configured, else the first ready."""
    if preferred:
        for backend in BACKENDS:
            if backend.id == preferred:
                if not backend.available():
                    raise SystemExit(
                        f"backend {preferred!r} was requested but its credential is not set")
                return backend
        raise SystemExit(f"unknown backend {preferred!r}; known: "
                         + ", ".join(b.id for b in BACKENDS))
    for backend in BACKENDS:
        if backend.available():
            return backend
    raise SystemExit(
        "no image-generation credential found. Set one of:\n"
        "  GEMINI_API_KEY       (Google AI Studio - free tier covers image models)\n"
        "  OPENROUTER_API_KEY   (OpenRouter)\n"
        "  OFOX_API_KEY         (OfoxAI relay)\n"
        f"Environment variables win; otherwise they are read from {CRED}")


def generate(prompt: str, model: str | None = None, out: str | Path | None = None,
             backend: str | None = None, retries: int = 3,
             timeout: int = 180) -> bytes:
    """Generate one image, write it to ``out`` if given, and return the bytes.

    Retries transient failures (network, 5xx, 429) with backoff. Auth and
    payment failures are raised immediately: retrying a 402 only burns time.
    """
    chosen = pick(backend)
    last: str | None = None
    for attempt in range(1, retries + 1):
        try:
            data = chosen.generate(prompt, model=model, timeout=timeout)
            if out is not None:
                target = Path(out)
                # Some backends answer JPEG regardless of the requested name; the
                # extension is corrected so downstream tooling never has to sniff.
                if target.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                    target = target.with_suffix(sniff(data))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            return data
        except Exception as exc:  # noqa: BLE001 - classify, then decide
            message = str(exc)
            last = message
            if any(code in message for code in ("401", "402", "403", "404 ")):
                break
            time.sleep(3 * attempt)
    raise RuntimeError(f"image generation failed via {chosen.label}: {last}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--list" in sys.argv or not args:
        for backend in BACKENDS:
            key = backend.available()
            state = f"ready ({key[:3]}...{key[-4:]})" if key else "not configured"
            print(f"  {backend.id:12s} {backend.label:42s} {state}")
        print(f"\n  default model per backend: {DEFAULT_MODEL}")
        return
    prompt = args[1] if len(args) > 1 else "a small red circle on a white background"
    out = args[0]
    data = generate(prompt, out=out)
    print(f"wrote {out} ({len(data) / 1024:.0f} KiB) via {pick().label}")


if __name__ == "__main__":
    main()
