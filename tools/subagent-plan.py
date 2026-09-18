#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Recommend a Doubao sub-agent configuration, and write it if asked.

Sub-agents in DSH are not separate agents you install. The child model is chosen
by the `subagent-model-selection` setting in `settings.yaml`:

    subagent-model-selection:
      enabled: true
      allowedModels: [ {provider, model}, ... ]

When a sub-agent tool call does not name a model, the child inherits the parent's
model; when it does, it must be in this allowlist. So "use Doubao for sub-agents"
means adding Doubao routes to that list — not installing anything.

The cost reasoning, which is the whole point:
  * A sub-agent is usually doing bounded, mechanical work — reading files,
    summarising, extracting, searching. Paying frontier prices for that is waste.
  * But a sub-agent that inherits the *parent's* model shares the parent's prompt
    cache; switching it to a different model family discards that reuse. So the
    cheap model is a win on token price and a small loss on cache hits, and the
    win is much larger whenever the child does real work.
  * Multi-modal children (who must read images) need a route with image input.

Usage:
    python tools/subagent-plan.py                 # recommend, show the YAML
    python tools/subagent-plan.py --write         # apply to settings.yaml
    python tools/subagent-plan.py --verify        # report the current setting
"""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

HOME = Path(os.environ.get("DSH_HOME", Path.home() / ".dsh"))
SETTINGS = HOME / "settings.yaml"

# Ordered by intent, not by price. Each entry is a route the ark-plan-api plugin
# actually defines, so the allowlist cannot name a provider that does not exist.
RECOMMENDED = [
    {
        "provider": "ark-cn",
        "model": "doubao-seed-2.1-turbo",
        "why": "默认子 agent。多模态、256k 上下文、按量付费里最快的档位。"
               "子 agent 做的是读书、抽信息、搜索这类机械活，用它是性价比最高的一档。",
        "when": "绝大多数子 agent 任务",
    },
    {
        "provider": "ark-cn",
        "model": "doubao-seed-2.1-pro",
        "why": "需要更强推理的子 agent（多步规划、复杂重构、代码审查）时用它。"
               "比 turbo 贵，但比前沿模型便宜很多。",
        "when": "子 agent 任务本身有难度时",
    },
    {
        "provider": "ark-cn",
        "model": "doubao-seed-evolving",
        "why": "1M 上下文。子 agent 要一次读进大量材料（整本论文、整个仓库）时用它，"
               "避免切块丢失上下文。",
        "when": "超长上下文任务",
    },
]

# Kept so the recommendation can point at them, but not enabled by default:
# plan routes only work if a subscription is active.
SUBSCRIPTION_ROUTES = {
    "ark-agent-plan-cn": "Agent Plan 订阅（未开通时调用会失败）",
    "ark-coding-plan-cn": "Coding Plan 订阅（未开通时调用会失败）",
}


def load_settings() -> dict:
    if not SETTINGS.exists():
        raise SystemExit(f"no settings file at {SETTINGS}")
    return yaml.safe_load(SETTINGS.read_text(encoding="utf-8")) or {}


def current() -> dict:
    data = load_settings()
    return data.get("subagent-model-selection") or {}


def verify() -> int:
    section = current()
    print(f"settings: {SETTINGS}")
    print(f"subagent-model-selection:")
    print(f"  enabled: {section.get('enabled')}")
    allowed = section.get("allowedModels") or []
    if not allowed:
        print("  allowedModels: (empty)")
    else:
        print(f"  allowedModels ({len(allowed)}):")
        for entry in allowed:
            if isinstance(entry, dict):
                print(f"    - {entry.get('provider')}/{entry.get('model')}")
            else:
                print(f"    - {entry}")
    ark = [e for e in allowed if isinstance(e, dict)
           and str(e.get("provider", "")).startswith("ark-")]
    print()
    if ark:
        print(f"{len(ark)} Ark route(s) already allowed.")
        return 0
    print("No Ark route is allowed yet, so sub-agents cannot use Doubao.")
    print("Run with --write to add the recommended set.")
    return 1


def write() -> int:
    data = load_settings()
    section = data.setdefault("subagent-model-selection", {})
    section["enabled"] = True
    allowed = section.setdefault("allowedModels", [])

    have = {(e.get("provider"), e.get("model")) for e in allowed if isinstance(e, dict)}
    added = []
    for entry in RECOMMENDED:
        key = (entry["provider"], entry["model"])
        if key in have:
            continue
        allowed.append({"provider": entry["provider"], "model": entry["model"]})
        added.append(key)

    if not added and section.get("enabled") is True:
        print("already configured; nothing to change")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = SETTINGS.with_name(f"{SETTINGS.name}.bak-{stamp}")
    shutil.copy2(SETTINGS, backup)
    SETTINGS.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                        encoding="utf-8", newline="\n")

    print(f"backup: {backup.name}")
    print(f"subagent-model-selection.enabled = true")
    for provider, model in added:
        print(f"  added: {provider}/{model}")
    print(f"allowedModels now has {len(allowed)} entry(ies)")
    return 0


def main() -> None:
    argv = sys.argv[1:]
    if "--verify" in argv:
        raise SystemExit(verify())
    if "--write" in argv:
        raise SystemExit(write())

    section = current()
    allowed = section.get("allowedModels") or []
    have = {(e.get("provider"), e.get("model")) for e in allowed if isinstance(e, dict)}

    print("=== 子 agent 模型怎么选 ===")
    print()
    print("机制：子 agent 的模型由 settings.yaml 的 subagent-model-selection 控制，")
    print("      不是另装一个 agent。白名单里的模型才能在子 agent 上显式指定；")
    print("      不指定时子 agent 继承父 agent 的模型。")
    print()
    print("代价：子 agent 与父 agent 同模型时可复用父级的 prompt 缓存；换成另一家")
    print("      会丢掉这部分复用。所以「便宜模型跑子 agent」在 token 单价上是赚的，")
    print("      在缓存命中上是小亏 —— 子 agent 实际干活越多，赚得越多。")
    print()
    print("=== 推荐加进白名单（都是按量付费路由，不需要订阅）===")
    for entry in RECOMMENDED:
        mark = "already allowed" if (entry["provider"], entry["model"]) in have else "to add"
        print()
        print(f"  {entry['provider']}/{entry['model']}   [{mark}]")
        print(f"    何时用：{entry['when']}")
        print(f"    理由：  {entry['why']}")
    print()
    print("=== 不建议默认开启 ===")
    for route, note in SUBSCRIPTION_ROUTES.items():
        print(f"  {route}: {note}")
    print()
    print("=== 要写进 settings.yaml 的内容 ===")
    print()
    merged = list(allowed)
    for entry in RECOMMENDED:
        if (entry["provider"], entry["model"]) not in have:
            merged.append({"provider": entry["provider"], "model": entry["model"]})
    print(yaml.safe_dump({"subagent-model-selection": {"enabled": True,
                                                       "allowedModels": merged}},
                         allow_unicode=True, sort_keys=False).rstrip())
    print()
    print("应用：python tools/subagent-plan.py --write")
    print("查看：python tools/subagent-plan.py --verify")


if __name__ == "__main__":
    main()
