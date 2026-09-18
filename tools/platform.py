#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Volcengine Ark adapters: Seedream (images) and Seedance (video).

Why this provider, when the project already had a relay backend: Ark is paid for
domestically (Alipay/WeChat), needs no overseas account or network path, and —
decisively for this project — is the only configured route that offers **video**
generation. Video is what makes a desktop pet's motion good: limbs articulate and
expressions change, which a deformed single drawing can never do.

Both APIs are documented at https://www.volcengine.com/docs/82379 and share the
same base URL and bearer auth:

* Images: ``POST /api/v3/images/generations`` — synchronous, returns one or more
  images. Reference images go in the ``image`` field, and multiple outputs come
  from ``sequential_image_generation``. That combination is what keeps a set of
  poses on-model: the model is shown the character instead of being described it.
* Video: ``POST /api/v3/contents/generations/tasks`` — asynchronous. It returns a
  task id; the task is polled until it succeeds and the clip is downloaded. A
  reference frame goes in ``content`` as an ``image_url``, so an animation can be
  seeded from the approved character sheet.

Keys are read from the environment or the DSH credential store, never written to
a file in the repository.

Usage:
    python platform.py --check                 # is a key present, and valid?
    python platform.py --list                  # models this module knows
    python platform.py --image out.png "prompt"
    python platform.py --video out.mp4 "prompt" --ref sheet.png
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from imggen import credential  # noqa: E402

BASE = "https://ark.cn-beijing.volces.com/api/v3"
KEY_NAMES = ("ARK_API_KEY", "VOLC_ACCESSKEY", "VOLCENGINE_API_KEY")

# Model ids as Ark spells them. The dated suffix is part of the id, and Ark
# rejects an id it does not know, so these are listed explicitly rather than
# built from a template.
IMAGE_MODELS = {
    "seedream-4.0": "doubao-seedream-4-0-250828",
    "seedream-5.0": "doubao-seedream-5-0-260128",
}
VIDEO_MODELS = {
    "seedance-2.0": "doubao-seedance-2-0-260128",
    "seedance-2.0-mini": "doubao-seedance-2-0-mini-260128",
}

DEFAULT_IMAGE_MODEL = IMAGE_MODELS["seedream-4.0"]
DEFAULT_VIDEO_MODEL = VIDEO_MODELS["seedance-2.0-mini"]

# Per-unit prices in CNY, used only to report and to stop a runaway batch. These
# are the provider's published rates, not a billing source of truth — the console
# is. They exist so a batch cannot silently spend more than the caller expected.
PRICE_PER_IMAGE = 0.20
PRICE_PER_VIDEO_SECOND = {"doubao-seedance-2-0-260128": 1.00,
                          "doubao-seedance-2-0-mini-260128": 0.50}


def estimate_images(count: int) -> float:
    return count * PRICE_PER_IMAGE


def estimate_video(model: str, seconds: int, clips: int) -> float:
    return clips * seconds * PRICE_PER_VIDEO_SECOND.get(model, 1.00)


class Budget:
    """A spending cap for one run.

    The point is not accounting — it is that a mistyped loop or a retry storm is
    the realistic way to lose money here, and the failure is silent until the
    console bill arrives. Every paid call goes through `spend`, which refuses
    once the cap is reached and says what it would have cost.
    """

    def __init__(self, limit: float, *, dry_run: bool = False, label: str = "run"):
        self.limit = float(limit)
        self.spent = 0.0
        self.calls = 0
        self.dry_run = dry_run
        self.label = label

    def spend(self, amount: float, what: str) -> None:
        if self.dry_run:
            self.spent += amount
            self.calls += 1
            print(f"  [dry-run] would spend CNY {amount:.2f} on {what} "
                  f"(running total CNY {self.spent:.2f})")
            return
        if self.spent + amount > self.limit + 1e-9:
            raise SystemExit(
                f"budget stop: {what} costs CNY {amount:.2f} but only "
                f"CNY {self.limit - self.spent:.2f} of the CNY {self.limit:.2f} "
                f"{self.label} budget is left.\n"
                f"  Raise it deliberately with --budget, or trim the batch.")
        self.spent += amount
        self.calls += 1
        print(f"  spend CNY {amount:.2f} on {what}  "
              f"(total CNY {self.spent:.2f} / CNY {self.limit:.2f})")

    def report(self) -> str:
        return (f"{self.label}: {self.calls} paid call(s), "
                f"CNY {self.spent:.2f} of CNY {self.limit:.2f}"
                + ("  [dry run, nothing was sent]" if self.dry_run else ""))


def api_key() -> str | None:
    """The Ark key, from the environment or the DSH credential store."""
    return credential(*KEY_NAMES)


def require_key() -> str:
    key = api_key()
    if not key:
        raise SystemExit(
            "no Volcengine Ark key found.\n"
            "  1. sign in at https://console.volcengine.com/ark and open 开通管理,\n"
            "     enable 图片生成 and (for animation) 视频生成\n"
            "  2. create an API key under API Key 管理\n"
            "  3. put it in the DSH credential store as ARK_API_KEY, or export it:\n"
            "       setx ARK_API_KEY \"your-key\"\n"
            f"  the credential store is {Path(os.environ.get('DSH_HOME', Path.home() / '.dsh')) / '.credentials.yaml'}")
    return key


def _headers(key: str, *, json_body: bool = True) -> dict:
    headers = {"Authorization": f"Bearer {key}"}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


# ---------------------------------------------------------------------------
# images — Seedream
# ---------------------------------------------------------------------------
def generate_image(prompt: str, model: str | None = None,
                   references: list[bytes | Path | str] | None = None,
                   size: str = "1024x1024", images: int = 1,
                   response_format: str = "b64_json", watermark: bool = False,
                   timeout: int = 240, budget: "Budget | None" = None) -> list[bytes]:
    """Generate one or more images, optionally conditioned on reference images.

    Returns the decoded bytes of every image produced.

    ``references`` is the important argument. Passing the approved character
    sheet here is what keeps a run on-model: the model is *shown* the character
    rather than asked to reconstruct it from prose, which is the failure mode
    the earlier text-only prompts kept hitting.
    """
    key = require_key()
    model = model or DEFAULT_IMAGE_MODEL
    if budget is not None:
        budget.spend(estimate_images(images), f"{images} image(s) via {model}")
        if budget.dry_run:
            return []
    body: dict = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "response_format": response_format,
        "watermark": watermark,
    }

    if references:
        encoded: list[str] = []
        for reference in references:
            raw = reference if isinstance(reference, bytes) else Path(reference).read_bytes()
            encoded.append("data:image/png;base64," + base64.b64encode(raw).decode())
        # One reference is a string, several are an array. Ark accepts both, but
        # the distinction is real: a single-element array is rejected by some
        # model versions.
        body["image"] = encoded[0] if len(encoded) == 1 else encoded

    if images > 1:
        # Seedream has no `n`. Multiple images come from the sequential mode,
        # which is a different feature: it keeps a consistent subject across the
        # set, which is exactly what a sprite sheet needs.
        body["sequential_image_generation"] = "auto"
        body["sequential_image_generation_options"] = {"max_images": images}

    r = requests.post(f"{BASE}/images/generations", headers=_headers(key),
                      json=body, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"Ark image generation HTTP {r.status_code}: {r.text[:500]}")
    payload = r.json()

    out: list[bytes] = []
    for item in payload.get("data") or []:
        if item.get("b64_json"):
            out.append(base64.b64decode(item["b64_json"]))
        elif item.get("url"):
            out.append(requests.get(item["url"], timeout=timeout).content)
    if not out:
        raise RuntimeError(f"Ark returned no image: {json.dumps(payload)[:400]}")
    return out


# ---------------------------------------------------------------------------
# video — Seedance
# ---------------------------------------------------------------------------
def create_video_task(prompt: str, model: str | None = None,
                      reference: bytes | Path | str | None = None,
                      duration: int = 5, resolution: str = "720p",
                      ratio: str = "1:1", generate_audio: bool = False,
                      watermark: bool = False, camera_fixed: bool = True,
                      return_last_frame: bool = True, timeout: int = 120,
                      budget: "Budget | None" = None) -> str:
    """Create an asynchronous video task; returns its id.

    ``camera_fixed`` defaults to true: a desktop-pet animation must hold the
    camera still, or the sprite drifts across its own frame and the matte
    alignment breaks. ``return_last_frame`` defaults to true because the last
    frame is what chains segments together into one continuous clip.

    Charging the budget happens here, at the one moment a task is actually
    submitted, so a caller that also goes through `generate_video` is not billed
    twice for the same task.
    """
    key = require_key()
    model = model or DEFAULT_VIDEO_MODEL
    if budget is not None:
        budget.spend(estimate_video(model, duration, 1),
                     f"one {duration}s clip via {model}")
        if budget.dry_run:
            return "dry-run-task"
    content: list[dict] = [{"type": "text", "text": prompt}]
    if reference is not None:
        raw = reference if isinstance(reference, bytes) else Path(reference).read_bytes()
        content.append({
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64," + base64.b64encode(raw).decode()},
        })

    body = {
        "model": model,
        "content": content,
        "duration": duration,
        "resolution": resolution,
        "ratio": ratio,
        "generate_audio": generate_audio,
        "watermark": watermark,
        "camera_fixed": camera_fixed,
        "return_last_frame": return_last_frame,
    }
    r = requests.post(f"{BASE}/contents/generations/tasks", headers=_headers(key),
                      json=body, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"Ark video task HTTP {r.status_code}: {r.text[:500]}")
    task_id = (r.json() or {}).get("id")
    if not task_id:
        raise RuntimeError(f"Ark returned no task id: {r.text[:300]}")
    return task_id


def poll_video_task(task_id: str, timeout: int = 900, interval: float = 5.0,
                    quiet: bool = False) -> dict:
    """Poll a task until it succeeds, fails, or the timeout expires.

    Reports progress by default. A generation takes minutes, and a silent wait is
    indistinguishable from a hang — which is exactly when a user starts
    re-submitting tasks and paying for them twice.
    """
    key = require_key()
    started = time.time()
    deadline = started + timeout
    last: dict = {}
    last_status = None
    while time.time() < deadline:
        r = requests.get(f"{BASE}/contents/generations/tasks/{task_id}",
                         headers=_headers(key, json_body=False), timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"Ark task poll HTTP {r.status_code}: {r.text[:300]}")
        last = r.json() or {}
        status = last.get("status")
        if not quiet and status != last_status:
            elapsed = int(time.time() - started)
            print(f"    task {task_id}: {status} ({elapsed}s elapsed)", flush=True)
            last_status = status
        elif not quiet and int(time.time() - started) % 30 < interval:
            print(f"    task {task_id}: still {status} "
                  f"({int(time.time() - started)}s)", flush=True)
        if status in ("succeeded", "failed", "cancelled"):
            return last
        time.sleep(interval)
    raise TimeoutError(f"task {task_id} still {last.get('status')!r} after {timeout}s")


def generate_video(prompt: str, out: str | Path, reference: bytes | Path | str | None = None,
                   budget: "Budget | None" = None, **kwargs) -> Path:
    """Create a task, wait for it, and download the clip to ``out``.

    A thin convenience over create + poll + fetch, so callers that just want a
    file do not have to re-implement the polling loop. The budget is charged by
    `create_video_task`, which is where the task is actually submitted.
    """
    task_id = create_video_task(prompt, reference=reference, budget=budget, **kwargs)
    if budget is not None and budget.dry_run:
        return Path(out)
    result = poll_video_task(task_id)
    if result.get("status") != "succeeded":
        raise RuntimeError(f"task {task_id} ended {result.get('status')}: "
                           f"{json.dumps(result)[:400]}")
    content = result.get("content") or {}
    url = content.get("video_url")
    if not url:
        raise RuntimeError(f"no video_url in {json.dumps(result)[:300]}")
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(requests.get(url, timeout=600).content)
    # The last frame is returned alongside the clip when requested; keeping it
    # next to the clip is what lets a long animation be built as a chain of
    # short segments that continue from one another.
    last_frame = content.get("last_frame_url")
    if last_frame:
        try:
            target.with_name(target.stem + "-last.png").write_bytes(
                requests.get(last_frame, timeout=300).content)
        except Exception:  # noqa: BLE001 - a missing last frame is not fatal
            pass
    return target


# ---------------------------------------------------------------------------
# video -> sprite frames
# ---------------------------------------------------------------------------
def video_to_frames(clip: Path, out_dir: Path, fps: int = 12,
                    background: str = "0x00FF00", tolerance: float = 0.22) -> list[Path]:
    """Freeze a green-screen clip into transparent PNG frames.

    The clip is generated on a flat chroma-key green, so the frames come out of
    here already matted — this is the same matte stage the image pipeline uses,
    with the same reasoning: alpha has to be produced by a key because neither
    WebM nor the encoder carries a usable alpha plane through this path.

    ``fps`` downsamples: generation is 24 fps, and a pet sprite at 24 fps is both
    heavier and unnecessary, so frames are picked rather than interpolated.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to freeze video into frames")
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.png"):
        stale.unlink()

    # colorkey on a green matte, for the reason recorded in tools/build_assets.py:
    # chromakey rewrites only the colour planes, so the encoder is handed an
    # opaque stream and the alpha is lost.
    vf = (f"[0:v]fps={fps},format=rgba,split=2[c][m];"
          f"[c]drawbox=x=0:y=0:w=iw:h=ih:color={background}@1.0:t=fill[cg];"
          f"[cg][m]overlay=format=auto,format=rgba,"
          f"colorkey={background}:{tolerance}:0.03,format=rgba")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(clip),
                    "-filter_complex", vf, str(out_dir / "%03d.png")], check=True)
    return sorted(out_dir.glob("*.png"))


# ---------------------------------------------------------------------------
def check() -> int:
    """Report whether a key is present and whether Ark accepts it."""
    key = api_key()
    if not key:
        print("ARK_API_KEY       not configured")
        print("\n" + "see `python tools/platform.py --check` docstring for setup steps")
        return 1
    print(f"ARK_API_KEY       configured ({key[:4]}...{key[-4:]})")
    try:
        r = requests.post(f"{BASE}/images/generations",
                          headers=_headers(key),
                          json={"model": DEFAULT_IMAGE_MODEL, "prompt": "a red dot",
                                "size": "512x512", "response_format": "b64_json",
                                "watermark": False},
                          timeout=180)
    except Exception as exc:  # noqa: BLE001
        print(f"connectivity      FAILED: {type(exc).__name__}: {str(exc)[:120]}")
        return 2
    if r.status_code == 200:
        print("image generation  OK")
        return 0
    print(f"image generation  HTTP {r.status_code}: {r.text[:300]}")
    if r.status_code in (401, 403):
        print("  -> the key is present but rejected. Check that 图片生成 is enabled")
        print("     for this account in the Ark console (开通管理).")
    return 2


def plan(budget_limit: float, *, clips: int, seconds: int, video_model: str,
         images: int, image_model: str) -> None:
    """Print what a batch would cost and stop — the cheapest useful command.

    Run this before topping up. It answers the only question that matters when
    money is tight: how much does the whole build cost, and which half of it is
    the expensive half.
    """
    image_cost = estimate_images(images)
    video_cost = estimate_video(video_model, seconds, clips)
    print(f"planned batch")
    print(f"  images  {images:3d} x CNY {PRICE_PER_IMAGE:.2f}  ({image_model})"
          f"   = CNY {image_cost:7.2f}")
    print(f"  video   {clips:3d} x {seconds}s ({video_model})"
          f"   = CNY {video_cost:7.2f}")
    total = image_cost + video_cost
    print(f"  {'':>31} total = CNY {total:7.2f}")
    print()
    if total > budget_limit:
        print(f"  OVER the CNY {budget_limit:.2f} budget by CNY {total - budget_limit:.2f}.")
        print("  Cheaper levers, most effective first:")
        print(f"    - drop the video stage entirely        saves CNY {video_cost:.2f}")
        print(f"    - video model -> seedance-2.0-mini     saves about half the video cost")
        print(f"    - {seconds}s -> 2s clips                     saves "
              f"CNY {video_cost - estimate_video(video_model, 2, clips):.2f}")
    else:
        print(f"  within the CNY {budget_limit:.2f} budget, "
              f"CNY {budget_limit - total:.2f} spare for retries")


def main() -> None:
    argv = sys.argv[1:]
    if "--check" in argv or (not argv and "--plan" not in argv):
        raise SystemExit(check())
    if "--list" in argv:
        print("image models:")
        for name, model_id in IMAGE_MODELS.items():
            print(f"  {name:20s} {model_id}")
        print("video models:")
        for name, model_id in VIDEO_MODELS.items():
            print(f"  {name:20s} {model_id}")
        return

    def option(flag: str, default, cast=str):
        return cast(argv[argv.index(flag) + 1]) if flag in argv else default

    if "--plan" in argv:
        plan(option("--budget", 10.0, float),
             clips=option("--clips", 13, int),
             seconds=option("--seconds", 2, int),
             video_model=option("--video-model", DEFAULT_VIDEO_MODEL),
             images=option("--images", 18, int),
             image_model=option("--image-model", DEFAULT_IMAGE_MODEL))
        return

    budget = Budget(option("--budget", 10.0, float),
                    dry_run="--dry-run" in argv,
                    label="this run")
    args = [a for a in argv if not a.startswith("--")
            and a not in (str(option("--budget", "")), str(option("--ref", "")))]

    if "--image" in argv:
        out = Path(args[0])
        prompt = args[1] if len(args) > 1 else "a plump calico cat on a green screen"
        images = generate_image(prompt, images=option("--n", 1, int), budget=budget)
        if images:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(images[0])
            print(f"wrote {out} ({len(images[0]) / 1024:.0f} KiB, "
                  f"{len(images)} image(s) returned)")
        print(budget.report())
        return

    if "--video" in argv:
        out = Path(args[0])
        prompt = args[1] if len(args) > 1 else "a cat sitting still"
        reference = Path(argv[argv.index("--ref") + 1]) if "--ref" in argv else None
        clip = generate_video(prompt, out, reference=reference, budget=budget,
                              duration=option("--seconds", 5, int),
                              model=option("--video-model", DEFAULT_VIDEO_MODEL))
        if clip.exists():
            print(f"wrote {clip} ({clip.stat().st_size / 1024:.0f} KiB)")
        print(budget.report())
        return

    raise SystemExit("nothing to do; see the module docstring for usage")


if __name__ == "__main__":
    main()
