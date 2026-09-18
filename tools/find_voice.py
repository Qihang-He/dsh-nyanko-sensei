#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Find downloadable character voice clips.

The pet's signature interaction is a click that speaks, and the package ships
only synthetic placeholders — the real line is a commercial recording. This
searches for openly reachable audio of the character so a *local* voice pack can
be assembled.

Scope note, because it matters: this writes only into ``work/``, which is
git-ignored. Nothing found here is ever committed or redistributed; the public
repository carries the synthetic placeholders and the voice-pack mechanism, and
the user supplies their own audio, exactly as the README describes.

Usage:
    python find_voice.py                 # search, list what it found
    python find_voice.py --download      # also save the audio it can fetch
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "work" / "voice-search"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
}

# Queries in both languages: the character is best covered on Japanese and
# Chinese sites, and the audio people actually share tends to be labelled with
# the localised name.
QUERIES = [
    "娘口三三 语音 なつめ 音声",
    "ニャンコ先生 なつめ ボイス 素材",
    "娘口三三 音效 叫声 mp3",
    "猫咪老师 语音包 下载",
    "nyanko sensei voice sound natsume mp3",
    "ニャンコ先生 ボイス フリー素材",
]

# Hosts that actually serve audio files, and the extensions worth looking for.
AUDIO_HOST_HINTS = (
    "soundeffect", "freesound", "myinstants", "bensound", "zapsplat",
    "cdn", "audio", "static", "media", "oss", "cloudfront", "bilibili",
    "hdslb", "ixigua", "douyin", "kuaishou", "weibo", "zhihu", "baidu",
)
AUDIO_EXT = (".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".flac", ".mp4")

# Direct-file patterns to scrape out of search-result and page HTML.
URL_PATTERNS = [
    re.compile(r'https?://[^\s"\'<>()]+?' + ext.replace(".", r"\.") + r'(?:\?[^\s"\'<>()]*)?',
               re.IGNORECASE)
    for ext in AUDIO_EXT
]
# Bing wraps result links in a redirect; the real target is in the query string.
BING_MEDIA = re.compile(r'"murl":"(.*?)"')
BING_PAGE = re.compile(r'"purl":"(.*?)"')


def bing_web(query: str, timeout: int = 40) -> str:
    url = f"https://cn.bing.com/search?q={quote_plus(query)}&count=30"
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    return r.text if r.status_code == 200 else ""


def bing_images(query: str, timeout: int = 40) -> list[str]:
    """Image-search HTML exposes a JSON blob with media URLs; audio hides there too."""
    url = f"https://cn.bing.com/images/search?q={quote_plus(query)}&count=35"
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    if r.status_code != 200:
        return []
    return [m.replace("\\/", "/") for m in BING_MEDIA.findall(r.text)]


def scrape_audio_urls(html: str) -> set[str]:
    found: set[str] = set()
    for pattern in URL_PATTERNS:
        for match in pattern.findall(html):
            url = match.replace("\\/", "/").replace("&amp;", "&")
            found.add(url)
    return found


def collect(download: bool) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    for query in QUERIES:
        print(f"\n=== {query}")
        pages: list[str] = []
        try:
            pages.append(bing_web(query))
        except Exception as exc:  # noqa: BLE001
            print(f"  web search failed: {type(exc).__name__}: {str(exc)[:100]}")
        try:
            for media in bing_images(query)[:40]:
                if media.endswith(AUDIO_EXT) or any(h in media for h in AUDIO_HOST_HINTS):
                    results.append({"query": query, "url": media, "stage": "image-index"})
        except Exception as exc:  # noqa: BLE001
            print(f"  image search failed: {type(exc).__name__}: {str(exc)[:100]}")

        for html in pages:
            for url in scrape_audio_urls(html):
                results.append({"query": query, "url": url, "stage": "html"})

    # Deduplicate, preferring URLs that end in a real audio extension.
    seen: dict[str, dict] = {}
    for item in results:
        key = item["url"]
        if key in seen:
            continue
        seen[key] = item
    ordered = sorted(seen.values(),
                     key=lambda i: (not i["url"].split("?")[0].lower().endswith(AUDIO_EXT),
                                    len(i["url"])))

    print(f"\n{len(ordered)} candidate audio URLs")
    for item in ordered[:40]:
        print(f"  [{item['stage']:11s}] {item['url'][:110]}")

    (OUT / "voice-urls.json").write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not download:
        print(f"\nlist written to {OUT / 'voice-urls.json'} (re-run with --download to fetch)")
        return

    raw = OUT / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    saved = 0
    for index, item in enumerate(ordered[:60]):
        if not item["url"].split("?")[0].lower().endswith(AUDIO_EXT):
            continue
        try:
            r = requests.get(item["url"], headers=HEADERS, timeout=60, stream=True)
            ctype = r.headers.get("content-type", "")
            if r.status_code != 200 or not ctype.startswith(("audio/", "video/", "application/octet")):
                continue
            suffix = Path(item["url"].split("?")[0]).suffix.lower() or ".bin"
            path = raw / f"clip-{index:03d}{suffix}"
            with path.open("wb") as handle:
                for chunk in r.iter_content(65536):
                    handle.write(chunk)
            if path.stat().st_size < 2048:
                path.unlink()
                continue
            item["local"] = path.name
            item["bytes"] = path.stat().st_size
            item["content_type"] = ctype
            saved += 1
            print(f"  saved {path.name}  {path.stat().st_size / 1024:.0f} KiB  {ctype}")
        except Exception as exc:  # noqa: BLE001 - one dead link must not stop the run
            print(f"  ! {item['url'][:70]} -> {type(exc).__name__}: {str(exc)[:70]}")

    (OUT / "voice-urls.json").write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{saved} audio files in {raw}")


if __name__ == "__main__":
    collect("--download" in sys.argv)
