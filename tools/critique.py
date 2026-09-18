#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Visual self-check: does the generated art actually look like the character?

The art pipeline generates from a written description, and a written description
is exactly the kind of thing that drifts. This closes the loop: the rendered
result is handed to a vision model together with the trait checklist derived from
the reference images, and it reports, trait by trait, whether the drawing matches.

This is a **aid to your own eyes, not a replacement for them** — run it after
looking at the output yourself. It also does not know which traits you care about
most, so weigh its report accordingly.

Usage:
    python critique.py [image ...]        # default: the built previews and views
    python critique.py work/views/front.png
    python critique.py --model google/gemini-3-pro
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ofox import describe_image  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# The checklist. Each entry is a trait observable in the reference images, paired
# with what the generator was told. Keep this in step with `CHAR` in gen_art.py:
# a trait that is not in CHAR cannot be expected to appear in the output, and a
# trait in CHAR that is not here goes unchecked.
TRAITS: list[tuple[str, str]] = [
    ("Forehead markings",
     "THREE bands across the forehead in this order: a wide ORANGE band on the "
     "viewer's left half, a narrow WHITE vertical divider down the centre, and a "
     "wide DARK GREY band on the viewer's right half that continues down over the "
     "right ear and the right side of the head. The white divider must be visible."),
    ("Eyes",
     "Narrow, thin, curved slit-like eyes that read as half-closed or closed in a "
     "sly smile. NOT large round eyes with big visible irises."),
    ("Body silhouette",
     "An egg / pear: narrow at the shoulders, widest at the hips and low belly, and "
     "very short overall. Short stubby legs are visible. NOT a perfect sphere."),
    ("Collar and bell",
     "A thin dark collar around the neck with a small round GOLD bell hanging from "
     "it at the front. This must be present."),
    ("Cheek marks",
     "Three short red-orange diagonal strokes on each cheek."),
    ("Mouth",
     "A thin curved line; often a wavy, slightly displeased shape rather than a "
     "simple smile."),
    ("Ears",
     "Large, tall, pointed triangular ears, angled slightly outward."),
    ("Body colour layout",
     "Orange over the back and the viewer's-left side and shoulder; dark grey over "
     "the upper back and the viewer's-right rump; chest, belly and all four paws "
     "clean white. Not scattered or random calico patches."),
    ("Face shape",
     "Wide and rather flat, broader than tall, with a white muzzle and white around "
     "both eyes."),
    ("Forbidden features",
     "There must be NO tabby stripes anywhere, NO raccoon-style rings or bands on "
     "the tail, and NO long thin legs or pointed snout."),
]

# Backends differ in how they name models; Google AI Studio takes the bare id.
DEFAULT_MODEL = "google/gemini-3.1-flash"


def build_question(with_reference: bool) -> str:
    lines = [
        "You are checking a drawing against a fixed character specification.",
        "",
        "For EACH numbered trait below, answer in exactly this format, one per line:",
        "  <number>. MATCH | MISMATCH | UNCLEAR - <one short sentence of evidence>",
        "",
        "Be literal and specific. Judge only what is visible. Do not be generous: if",
        "the trait is absent or only partly present, answer MISMATCH or UNCLEAR.",
        "After the list, add a final section 'TOP FIXES:' with at most three concrete",
        "changes to the drawing instructions that would most improve the likeness.",
        "",
        "Checklist:",
    ]
    for index, (name, detail) in enumerate(TRAITS, start=1):
        lines.append(f"{index}. {name}: {detail}")
    if with_reference:
        lines += [
            "",
            "A reference image of the character follows the drawing. Compare the two "
            "directly.",
        ]
    return "\n".join(lines)


def critique(image: Path, model: str, reference: Path | None = None) -> str:
    from ofox import api_key  # noqa: F401 - fails early with a clear message

    question = build_question(reference is not None)
    if reference is None:
        return describe_image(image, question, model=model)
    # Two images in one turn: the drawing first, the reference second.
    import base64

    import requests

    from ofox import BASE, _headers

    def data_url(path: Path) -> str:
        return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()

    body = {
        "model": model,
        "max_tokens": 1200,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": data_url(image)}},
                {"type": "image_url", "image_url": {"url": data_url(reference)}},
            ],
        }],
    }
    r = requests.post(f"{BASE}/chat/completions", headers=_headers(), json=body, timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"critique failed HTTP {r.status_code}: {r.text[:300]}")
    return (r.json()["choices"][0]["message"].get("content") or "").strip()


def default_targets() -> list[Path]:
    """Everything worth looking at, in the order a human would review it."""
    found: list[Path] = []
    for directory in (ROOT / "work" / "views", ROOT / "work" / "sheets",
                      ROOT / "work" / "candidates"):
        if directory.is_dir():
            found += sorted(p for p in directory.iterdir()
                            if p.suffix.lower() in (".png", ".jpg", ".webp"))
    return found


def main() -> None:
    argv = sys.argv[1:]
    model = DEFAULT_MODEL
    if "--model" in argv:
        index = argv.index("--model")
        model = argv[index + 1]
        del argv[index:index + 2]

    reference = None
    if "--reference" in argv:
        index = argv.index("--reference")
        reference = Path(argv[index + 1])
        del argv[index:index + 2]

    targets = [Path(a) for a in argv] or default_targets()
    if not targets:
        raise SystemExit("nothing to critique: no images in work/views, work/sheets "
                         "or work/candidates. Run gen_art.py first.")

    for target in targets:
        print("=" * 78)
        print(f"{target.relative_to(ROOT) if target.is_absolute() else target}"
              + (f"   vs {reference.name}" if reference else ""))
        print("=" * 78)
        try:
            print(critique(target, model, reference))
        except Exception as exc:  # noqa: BLE001 - one bad image must not stop the run
            print(f"  ! critique failed: {str(exc)[:300]}")
        print()


if __name__ == "__main__":
    main()
