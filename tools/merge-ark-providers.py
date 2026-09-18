#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Merge the Ark provider routes into a profile's own patch layer.

Why this is needed at all, because it is a trap worth writing down:

`ark-plan-api` contributes its providers by patching the `llm-pi-ai` row at the
**bundle** layer. DSH applies the profile's own `cordis.patch.yml` **after** every
bundle layer, and a patch replaces a row's `config` wholesale rather than
deep-merging it (the profile patch file says so itself). So if the profile also
patches `llm-pi-ai` — which this one does, to add the ofox relay — the profile's
version wins and the Ark routes are silently erased. Nothing errors; the
providers simply are not there.

The fix is to put the Ark routes in the layer that actually wins. This script
reads them out of the plugin's own `cordis.patch.yml` rather than restating them,
so the two cannot drift when the plugin is updated.

Usage:
    python tools/merge-ark-providers.py                 # dry run, shows the diff
    python tools/merge-ark-providers.py --write         # apply, with a backup
    python tools/merge-ark-providers.py --verify        # is llm-pi-ai patched twice?
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

HOME = Path(os.environ.get("DSH_HOME", Path.home() / ".dsh"))
PROFILE_PATCH = HOME / "profiles" / "web" / "cordis.patch.yml"
PLUGIN_PATCHES = list((HOME / "ark-plugins").glob("*/ark-plan-api-*.tgz"))

# Routes that only work with a plan subscription. They are kept because they cost
# nothing to carry and show up as options, but the pay-as-you-go route is the one
# an à-la-carte account uses.
ROUTE_NOTES = {
    "ark-cn": "后付费 API (cn-beijing) — 按量付费开通的 Seedream/Seedance 走这条",
    "ark-agent-plan-cn": "Agent Plan 订阅",
    "ark-coding-plan-cn": "Coding Plan 订阅",
    "ark-coding-plan-byteplus": "Coding Plan 海外 (BytePlus)",
    "ark-byteplus": "后付费 海外 (BytePlus)",
}


def plugin_patch_text() -> str:
    """The Ark plugin's cordis.patch.yml, read out of its tarball."""
    import tarfile

    if not PLUGIN_PATCHES:
        raise SystemExit(f"no ark-plan-api tarball under {HOME / 'ark-plugins'}")
    newest = sorted(PLUGIN_PATCHES)[-1]
    with tarfile.open(newest) as tf:
        member = next((m for m in tf.getmembers() if m.name.endswith("cordis.patch.yml")), None)
        if member is None:
            raise SystemExit(f"no cordis.patch.yml inside {newest}")
        return tf.extractfile(member).read().decode("utf-8")


def ark_providers() -> dict:
    """The `providers:` map the Ark plugin declares, as data."""
    doc = yaml.safe_load(plugin_patch_text())
    for entry in doc:
        if entry.get("id") == "llm-pi-ai":
            return (entry.get("config") or {}).get("providers") or {}
    raise SystemExit("the Ark plugin patch has no llm-pi-ai entry")


def load_profile_patch() -> list:
    text = PROFILE_PATCH.read_text(encoding="utf-8")
    # The file is heavily commented; safe_load keeps only the data, and the
    # comments are preserved separately because the rewrite is textual.
    return yaml.safe_load(text) or []


def find_pi_ai_entry(doc: list) -> dict | None:
    for entry in doc:
        if isinstance(entry, dict) and entry.get("id") == "llm-pi-ai":
            return entry
    return None


def verify() -> int:
    doc = load_profile_patch()
    entry = find_pi_ai_entry(doc)
    if entry is None:
        print("the profile patch does not touch llm-pi-ai at all.")
        print("  -> the bundle-layer Ark routes apply normally; nothing to merge.")
        return 0
    providers = ((entry.get("config") or {}).get("providers")) or {}
    ark = [k for k in providers if k.startswith("ark-")]
    print(f"the profile patch DOES replace llm-pi-ai config "
          f"({len(providers)} provider(s): {', '.join(providers) or 'none'})")
    if ark:
        print(f"  Ark routes present in the winning layer: {', '.join(ark)}")
        print("  -> OK; the bundle patch is redundant but harmless.")
        return 0
    print("  NO Ark routes in the winning layer.")
    print("  -> the bundle-layer patch is being erased. Run this script with --write.")
    return 1


def entry_span(text: str, entry_id: str) -> tuple[int, int] | None:
    """Line span of a top-level patch entry, as (start, end_exclusive).

    Needed because the merge has to happen *inside* the `llm-pi-ai` entry, and
    entries are separated by comment blocks. Appending to the end of the file
    instead — the obvious approach — silently nests the new providers under
    whatever entry happens to be last, which parses fine and does nothing. That
    is exactly the bug this function exists to avoid.
    """
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(rf"^- id:\s*{re.escape(entry_id)}\s*$", line):
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("- "):
            end = index
            break
    return start, end


def render_entry(entry_id: str, providers: dict) -> str:
    """Serialize one patch entry as YAML text, in the file's own style."""
    body = yaml.safe_dump({"id": entry_id, "config": {"providers": providers}},
                          allow_unicode=True, sort_keys=False, default_flow_style=False)
    # `id:` must be the list item marker, not a mapping key.
    body = body.replace("id: " + entry_id, "- id: " + entry_id, 1)
    # The file indents sequence items under a key by two spaces (`models:` then
    # `  - id:`). PyYAML's default is zero, which is legal but inconsistent with
    # everything around it and unpleasant to read.
    body = re.sub(r"^(\s*)(- )", r"\1  \2", body, flags=re.MULTILINE)
    return body


def write_merge() -> int:
    providers = ark_providers()
    doc = load_profile_patch()
    entry = find_pi_ai_entry(doc)
    if entry is None:
        raise SystemExit("the profile patch has no llm-pi-ai entry to extend; add one "
                         "by hand, or delete it so the bundle layer applies")

    existing = ((entry.get("config") or {}).get("providers")) or {}
    added = [name for name in providers if name not in existing]
    if not added:
        print("all Ark routes are already present; nothing to do")
        return 0

    original = PROFILE_PATCH.read_text(encoding="utf-8")
    if not original.endswith("\n"):
        original += "\n"
    lines = original.splitlines()

    span = entry_span(original, "llm-pi-ai")
    if span is None:
        raise SystemExit("could not locate the llm-pi-ai entry as a top-level item")
    start, end = span

    # Find `providers:` inside that entry and the first key under it, so the new
    # providers can be spliced in as siblings at exactly the same indentation.
    # Inserting there — rather than rebuilding the whole entry — keeps every
    # existing comment and the ofox block byte-for-byte intact, which matters
    # because this file is mostly hand-written explanation.
    providers_line = next((i for i in range(start, end)
                           if lines[i].strip() == "providers:"), None)
    if providers_line is None:
        raise SystemExit("the llm-pi-ai entry has no `providers:` key to extend")

    indent = None
    anchor = end
    for i in range(providers_line + 1, end):
        stripped = lines[i].lstrip()
        if stripped and not stripped.startswith("#"):
            indent = len(lines[i]) - len(stripped)
            anchor = i
            break
    if indent is None:
        raise SystemExit("`providers:` is empty; add the first provider by hand")

    header_lines = [
        f"{' ' * (indent - 2)}# --- 火山方舟 (Volcengine Ark) -------------------------------------------",
        f"{' ' * (indent - 2)}# 为什么必须写在这里：ark-plan-api 插件在 **bundle 层**给 llm-pi-ai 打补丁，",
        f"{' ' * (indent - 2)}# 而 profile 层补丁在其后应用，且 config 是「整体替换」而非深合并 —— 所以",
        f"{' ' * (indent - 2)}# 本文件这个 providers 块会把 bundle 层的 ark 路由整个抹掉，且不报错。",
        f"{' ' * (indent - 2)}# 由 tools/merge-ark-providers.py 从插件自身的 cordis.patch.yml 抄写并原位合并；",
        f"{' ' * (indent - 2)}# 插件升级后重跑该脚本，不要手改。",
        f"{' ' * (indent - 2)}# 密钥在 Web 的「模型」设置页按 provider 填，凭据名见各条 apiKeyEnv。",
        f"{' ' * (indent - 2)}# 按量付费（开通了 Seedream / Seedance）用 ark-cn -> ARK_CN_API_KEY。",
    ]
    header_lines += [f"{' ' * (indent - 2)}#   {name:28s} -> {providers[name].get('apiKeyEnv')}"
                     for name in added]

    block = yaml.safe_dump({name: providers[name] for name in added},
                           allow_unicode=True, sort_keys=False, default_flow_style=False)
    # `indent` is the column the provider keys sit at. PyYAML's dump nests each
    # level by two spaces, and `- id:` occurs at *two* of those levels (a
    # provider, and each entry of its `models` list), so mapping by prefix is
    # wrong — it collides the two. Mapping by exact leading-space count is
    # unambiguous: 0 -> indent, 2 -> indent+2, 4 -> indent+4, and so on.
    body: list[str] = [
        (" " * (indent + len(line) - len(line.lstrip())) + line.lstrip()) if line.strip() else ""
        for line in block.splitlines()
    ]

    result = lines[:anchor] + header_lines + body + lines[anchor:]
    merged = "\n".join(result) + "\n"

    # Validate before writing: a malformed patch file makes DSH fail to boot,
    # which is a far worse outcome than not applying the merge.
    try:
        check = yaml.safe_load(merged)
    except yaml.YAMLError as exc:
        raise SystemExit(f"the merged file would not parse, refusing to write: {exc}")
    check_entry = find_pi_ai_entry(check)
    got = list(((check_entry or {}).get("config") or {}).get("providers") or {})
    missing = [n for n in providers if n not in got]
    if missing:
        raise SystemExit(f"validation failed: {missing} missing after merge")
    for must_keep in ("ofox",):
        if must_keep not in got:
            raise SystemExit(f"validation failed: the {must_keep} provider was lost")
    for must_keep in ("permission-rules", "llm-deepseek"):
        if not find_entry(check, must_keep):
            raise SystemExit(f"validation failed: the {must_keep} entry was lost")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = PROFILE_PATCH.with_name(f"{PROFILE_PATCH.name}.bak-{stamp}")
    shutil.copy2(PROFILE_PATCH, backup)
    PROFILE_PATCH.write_text(merged, encoding="utf-8", newline="\n")

    print(f"backup: {backup.name}")
    print(f"added {len(added)} Ark route(s): {', '.join(added)}")
    print(f"providers in the winning layer are now: {', '.join(got)}")
    print()
    print("Next: restart the host so the composed config is rebuilt, then set the key")
    print("on the Web Models page (credential name: "
          f"{providers.get('ark-cn', {}).get('apiKeyEnv', 'ARK_CN_API_KEY')}).")
    return 0


def find_entry(doc: list, entry_id: str) -> dict | None:
    for entry in doc or []:
        if isinstance(entry, dict) and entry.get("id") == entry_id:
            return entry
    return None


def main() -> None:
    argv = sys.argv[1:]
    if "--verify" in argv:
        raise SystemExit(verify())
    if "--write" in argv:
        raise SystemExit(write_merge())

    # Default: dry run, showing exactly what would be added.
    providers = ark_providers()
    doc = load_profile_patch()
    entry = find_pi_ai_entry(doc)
    existing = list(((entry or {}).get("config") or {}).get("providers") or {})
    print(f"profile patch: {PROFILE_PATCH}")
    print(f"providers currently in the winning layer: {', '.join(existing) or 'none'}")
    print(f"Ark routes the plugin defines: {', '.join(providers)}")
    to_add = [n for n in providers if n not in existing]
    print()
    if to_add:
        print(f"would add: {', '.join(to_add)}")
        for name in to_add:
            note = ROUTE_NOTES.get(name, "")
            print(f"  {name:28s} -> {providers[name].get('apiKeyEnv'):32s} {note}")
        print("\nre-run with --write to apply (a backup is taken first)")
    else:
        print("nothing to add; the winning layer already has every Ark route")


if __name__ == "__main__":
    main()
