#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Put a provider key into the DSH credential store, safely.

Three things this is careful about, because a leaked key is worse than a missing
one:

* The key is typed into a local prompt, not passed as an argument and not pasted
  into a chat window. Command-line arguments end up in shell history and in
  process listings; a chat window ends up in the session transcript.
* The store is backed up before it is edited, and rewritten as valid YAML through
  a parser rather than by string surgery, so a comment or an unusual key in the
  existing file cannot be corrupted.
* Only a masked form is ever printed.

Usage:
    python tools/set-key.py ARK_API_KEY
    python tools/set-key.py ARK_API_KEY --from-env        # read $env:ARK_API_KEY
    python tools/set-key.py --list                        # show what is configured
    python tools/set-key.py ARK_API_KEY --show-config     # print the key name only
"""
from __future__ import annotations

import getpass
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

HOME = Path(os.environ.get("DSH_HOME", Path.home() / ".dsh"))
STORE = HOME / ".credentials.yaml"

# Keys this project knows how to use, and where each is read from.
KNOWN = {
    "ARK_API_KEY": "Volcengine Ark - Seedream images, Seedance video (tools/platform.py)",
    "GEMINI_API_KEY": "Google AI Studio - Gemini images (tools/imggen.py, needs a proxy)",
    "OPENROUTER_API_KEY": "OpenRouter - Gemini images via relay (tools/imggen.py)",
    "OFOX_API_KEY": "OfoxAI relay - images and vision (tools/imggen.py, tools/ofox.py)",
}


def load() -> dict:
    if not STORE.exists():
        raise SystemExit(f"no credential store at {STORE}")
    return yaml.safe_load(STORE.read_text(encoding="utf-8")) or {}


def mask(value: str) -> str:
    value = str(value)
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]} (len {len(value)})"


def list_keys() -> None:
    data = load()
    refs = data.get("refs") or {}
    print(f"store: {STORE}\n")
    if not refs:
        print("  (no keys configured)")
        return
    for name, value in refs.items():
        note = KNOWN.get(name, "not used by this project")
        print(f"  {name:20s} {mask(value)}")
        print(f"  {'':20s} {note}")


def set_key(name: str, value: str) -> None:
    value = value.strip()
    if not value:
        raise SystemExit("empty value; nothing written")
    if any(ch.isspace() for ch in value):
        raise SystemExit("the value contains whitespace — check that the paste "
                         "did not include a line break")

    data = load()
    refs = data.setdefault("refs", {})
    existed = name in refs

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = STORE.with_name(f"{STORE.name}.bak-{stamp}")
    shutil.copy2(STORE, backup)
    print(f"backup written: {backup.name}")

    refs[name] = value
    # Dumped through the parser, so the rest of the file survives even if it was
    # hand-edited with comments or unusual formatting.
    STORE.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                     encoding="utf-8", newline="\n")

    verb = "updated" if existed else "added"
    print(f"{verb}: {name} = {mask(value)}")
    print(f"store:   {STORE}")
    print()
    print("Next:")
    if name == "ARK_API_KEY":
        print("  python tools/platform.py --check")
        print("  python tools/spend_plan.py")
    else:
        print("  python tools/imggen.py --list")


def main() -> None:
    argv = sys.argv[1:]
    if not argv or "--list" in argv:
        list_keys()
        if not argv:
            print("\nusage: python tools/set-key.py <KEY_NAME> [--from-env]")
            print("known keys:")
            for name, note in KNOWN.items():
                print(f"  {name:20s} {note}")
        return

    name = next((a for a in argv if not a.startswith("--")), None)
    if not name:
        raise SystemExit("no key name given; try --list")

    if "--from-env" in argv:
        value = os.environ.get(name, "")
        if not value:
            raise SystemExit(f"${name} is not set in this shell")
        set_key(name, value)
        return

    if "--stdin" in argv:
        # Explicit, so it can never happen by accident: reading a secret from a
        # pipe is fine, but blocking on a hidden prompt when stdin is a pipe is
        # not, and `getpass` does exactly that.
        value = sys.stdin.readline()
        if not value.strip():
            raise SystemExit("nothing on stdin")
        set_key(name, value)
        return

    if "--show-config" in argv:
        print(f"add this under `refs:` in {STORE}:")
        print(f"  {name}: <your key>")
        return

    if not sys.stdin.isatty():
        raise SystemExit(
            "this needs an interactive terminal to read the key without echoing it.\n"
            "alternatives:\n"
            f"  echo <your-key> | python tools/set-key.py {name} --stdin\n"
            f"  set {name}=<your-key>  then  python tools/set-key.py {name} --from-env")

    print(f"store: {STORE}")
    print(f"setting: {name}")
    if name in KNOWN:
        print(f"purpose: {KNOWN[name]}")
    print()
    value = getpass.getpass("paste the key (input hidden, press Enter): ")
    set_key(name, value)


if __name__ == "__main__":
    main()
