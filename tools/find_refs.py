#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Find high-quality character art, and score it for use as a generation reference.

The earlier search produced 529 files and not one usable reference, and the
reason was the ranking, not the sources: it scored whatever image search
returned, so merchandise photos, stickers and unrelated cats ranked as highly as
real art. What actually makes a good reference is narrow and measurable:

* **resolution** — the previous reference was 180x240, which is why the first
  Seedream output had a fuzzy green-tinted outline. The model can only draw the
  character it is shown.
* **an alpha channel or a plain background** — a pre-cut PNG composites
  predictably as a reference; a photograph of a plush toy does not.
* **the character's colour signature** — mostly cream, meaningful orange AND
  grey, almost no green or blue. A tabby, a white cat with no markings, or a
  blue-sky scene all fail this.
* **proportions** — a full-body or head-and-shoulders framing, not a wide
  screenshot with the character small in one corner.

Usage:
    python find_refs.py --search          # query Bing, download, score
    python find_refs.py --folder DIR      # score images already on disk
    python find_refs.py --sheet           # contact sheet of the best candidates
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from urllib.parse import quote_plus

import numpy as np
import requests
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "work" / "refsearch"
RAW = OUT / "raw"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
}

# Targeted at clean single-character art. "png" and "透明" bias toward pre-cut
# images; the franchise and character names are given in both languages because
# the best art tends to be tagged in Japanese or Chinese.
QUERIES = [
    "ニャンコ先生 公式 全身 立ち絵 高画質",
    "娘口三三 官方 立绘 全身 高清 png 透明",
    "猫咪老师 全身 正面 设定图 白底",
    "nyanko sensei transparent png full body",
    "ニャンコ先生 イラスト 透過 png 全身",
    "夏目友人帳 ニャンコ先生 キャラクター 設定画",
]

# Bing encodes the JSON it embeds in the results page, so the useful fields
# arrive as `&quot;murl&quot;:&quot;...&quot;` rather than `"murl":"..."`. An
# earlier version of this file matched the unencoded form, found zero URLs on
# every query, and looked exactly like a rate limit or a dead provider.
BING_MEDIA = __import__("re").compile(r"&quot;murl&quot;:&quot;(.*?)&quot;")
BING_TITLE = __import__("re").compile(r"&quot;t&quot;:&quot;(.*?)&quot;")


def _unescape(value: str) -> str:
    import html

    return html.unescape(value).replace("\\/", "/")


def bing_image_urls(query: str, timeout: int = 40) -> list[tuple[str, str]]:
    url = f"https://cn.bing.com/images/search?q={quote_plus(query)}&count=60"
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    if r.status_code != 200:
        return []
    html = r.text
    media = [_unescape(m) for m in BING_MEDIA.findall(html)]
    titles = [_unescape(t) for t in BING_TITLE.findall(html)]
    return list(zip(media, titles + [""] * len(media)))


def score(image: Image.Image) -> dict:
    """How suitable is this image as a generation reference?"""
    width, height = image.size
    rgba = image.convert("RGBA")
    alpha = np.asarray(rgba)[..., 3]
    has_alpha = bool((alpha < 250).mean() > 0.05)

    arr = np.asarray(rgba.convert("RGB")).astype(np.float32)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    maximum = np.maximum(np.maximum(r, g), b)
    minimum = np.minimum(np.minimum(r, g), b)
    sat = np.where(maximum > 1e-6, (maximum - minimum) / np.maximum(maximum, 1e-6), 0.0)
    total = arr.shape[0] * arr.shape[1]

    cream = float(((maximum > 190) & (sat < 0.18)).mean())
    orange = float(((r > g) & (g > b) & (r - b > 55) & (sat > 0.35)).mean())
    grey = float(((sat < 0.12) & (maximum > 70) & (maximum < 195)).mean())
    green = float(((g - np.maximum(r, b)) > 18).mean())
    blue = float(((b - np.maximum(r, g)) > 18).mean())

    # The character needs cream in quantity and BOTH accent patches; requiring
    # orange and grey together is what excludes white cats and plain tabbies.
    signature = min(orange, grey)
    pixels = width * height
    resolution = min(1.0, (pixels / (900 * 900)) ** 0.5)

    value = (cream * 2.2
             + min(orange, 0.35) * 2.2
             + min(grey, 0.35) * 2.2
             + min(signature, 0.12) * 7.0
             - green * 2.6
             - blue * 2.6
             + resolution * 1.4
             + (0.5 if has_alpha else 0.0))

    # A reference needs the subject to fill the frame; a wide screenshot with a
    # small character in it teaches the model nothing about proportions.
    aspect = max(width, height) / max(1, min(width, height))
    if aspect > 2.0:
        value -= 0.8

    return {
        "size": [width, height],
        "megapixels": round(pixels / 1e6, 2),
        "has_alpha": has_alpha,
        "cream": round(cream, 3),
        "orange": round(orange, 3),
        "grey": round(grey, 3),
        "green": round(green, 3),
        "blue": round(blue, 3),
        "aspect": round(aspect, 2),
        "score": round(float(value), 3),
    }


def from_search(min_side: int = 500) -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    seen: set[str] = set()

    for query in QUERIES:
        print(f"\n=== {query}")
        try:
            urls = bing_image_urls(query)
        except Exception as exc:  # noqa: BLE001
            print(f"  search failed: {type(exc).__name__}: {str(exc)[:90]}")
            continue
        print(f"  {len(urls)} candidate URL(s)")
        for index, (url, title) in enumerate(urls[:45]):
            if url in seen:
                continue
            seen.add(url)
            try:
                r = requests.get(url, headers=HEADERS, timeout=30)
                if r.status_code != 200 or not r.headers.get(
                        "content-type", "").startswith("image"):
                    continue
                image = Image.open(io.BytesIO(r.content))
                if min(image.size) < min_side:
                    continue
                record = score(image)
                record["url"] = url
                record["title"] = title[:90]
                record["query"] = query
                entries.append(record)
            except Exception:  # noqa: BLE001 - a dead link is not interesting
                continue
        print(f"  kept {len(entries)} so far")

    entries.sort(key=lambda e: -e["score"])
    for rank, entry in enumerate(entries[:60]):
        try:
            r = requests.get(entry["url"], headers=HEADERS, timeout=30)
            suffix = ".png" if r.content[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
            path = RAW / f"ref-{rank:03d}{suffix}"
            path.write_bytes(r.content)
            entry["local"] = path.name
        except Exception:  # noqa: BLE001
            continue
    (OUT / "candidates.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return entries


def from_folder(folder: Path) -> list[dict]:
    entries = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            continue
        try:
            image = Image.open(path)
        except Exception:  # noqa: BLE001
            continue
        record = score(image)
        record["local"] = path.name
        record["url"] = str(path)
        entries.append(record)
    entries.sort(key=lambda e: -e["score"])
    return entries


def contact_sheet(entries: list[dict], folder: Path, top: int = 24,
                  cols: int = 6, cell: int = 220) -> Path | None:
    usable = [e for e in entries if e.get("local") and (folder / e["local"]).exists()][:top]
    if not usable:
        return None
    rows = (len(usable) + cols - 1) // cols
    label = 22
    sheet = Image.new("RGB", (cell * cols, (cell + label) * rows), (22, 22, 26))
    draw = ImageDraw.Draw(sheet)
    for index, entry in enumerate(usable):
        try:
            image = Image.open(folder / entry["local"]).convert("RGB")
        except Exception:  # noqa: BLE001
            continue
        image.thumbnail((cell, cell), Image.LANCZOS)
        x = (index % cols) * cell + (cell - image.width) // 2
        y = (index // cols) * (cell + label) + (cell - image.height) // 2
        sheet.paste(image, (x, y))
        draw.text(((index % cols) * cell + 4, (index // cols) * (cell + label) + cell + 3),
                  f"{entry['local']} {entry['score']:.2f} "
                  f"{'A' if entry['has_alpha'] else ' '}",
                  fill=(210, 210, 218))
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "sheet.png"
    sheet.save(out)
    return out


def main() -> None:
    argv = sys.argv[1:]
    folder = RAW
    if "--folder" in argv:
        folder = Path(argv[argv.index("--folder") + 1])
        entries = from_folder(folder)
    else:
        entries = from_search()

    print(f"\n{'file':16s} {'size':>12s} {'score':>6s} {'alpha':>5s} "
          f"{'cream':>6s} {'orange':>6s} {'grey':>6s} {'green':>6s}   title")
    for entry in entries[:40]:
        print(f"{str(entry.get('local', ''))[:16]:16s} {str(entry['size']):>12s} "
              f"{entry['score']:>6.2f} {'yes' if entry['has_alpha'] else 'no':>5s} "
              f"{entry['cream']:>6.3f} {entry['orange']:>6.3f} {entry['grey']:>6.3f} "
              f"{entry['green']:>6.3f}   {str(entry.get('title', ''))[:52]}")

    sheet = contact_sheet(entries, folder)
    if sheet:
        print(f"\ncontact sheet: {sheet}")


if __name__ == "__main__":
    main()
