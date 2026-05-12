#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "用量总览",
#   "name@zh-Hans": "用量总览",
#   "name@en": "Usage Overview",
#   "icon": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/openai.png",
#   "description": "聚合 Claude / Gemini / Codex 今日所有模型的 token 用量",
#   "description@zh-Hans": "聚合 Claude / Gemini / Codex 今日所有模型的 token 用量",
#   "description@en": "Aggregate today's token usage across Claude / Gemini / Codex by model",
#   "parameters": [
#     {
#       "name": "CLAUDE_DIR",
#       "label": "Claude 数据目录",
#       "label@zh-Hans": "Claude 数据目录",
#       "label@en": "Claude Data Dir",
#       "type": "string",
#       "required": false,
#       "defaultValue": "~/.claude/projects"
#     },
#     {
#       "name": "GEMINI_DIR",
#       "label": "Gemini 数据目录",
#       "label@zh-Hans": "Gemini 数据目录",
#       "label@en": "Gemini Data Dir",
#       "type": "string",
#       "required": false,
#       "defaultValue": "~/.gemini/tmp"
#     },
#     {
#       "name": "CODEX_DIR",
#       "label": "Codex 数据目录",
#       "label@zh-Hans": "Codex 数据目录",
#       "label@en": "Codex Data Dir",
#       "type": "string",
#       "required": false,
#       "defaultValue": "~/.codex"
#     },
#     {
#       "name": "TOKEN_MODE",
#       "label": "Token 计算口径（仅对 Claude 生效）",
#       "label@zh-Hans": "Token 计算口径（仅对 Claude 生效）",
#       "label@en": "Token Counting Mode (Claude only)",
#       "type": "choice",
#       "required": false,
#       "defaultValue": "billable",
#       "options": [
#         {"label": "计费等价（input+output+cache_creation）", "label@zh-Hans": "计费等价（input+output+cache_creation）", "label@en": "Billable (input+output+cache_creation)", "value": "billable"},
#         {"label": "原始（含 cache_read 命中）", "label@zh-Hans": "原始（含 cache_read 命中）", "label@en": "Raw (incl. cache_read hits)", "value": "raw"}
#       ]
#     }
#   ]
# }
# /UsageBoardPlugin
"""聚合 Claude / Gemini / Codex 今日的 token 用量（仅今日，无 period 切换）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from _shared import (  # noqa: E402
    SCHEMA_VERSION,
    build_overview_dimension,
    lang,
    normalize_token_mode,
    parse_params,
    utc_now_iso,
)


def main() -> int:
    p = parse_params(sys.argv[1:])
    language = lang(p)
    claude_dir = p.get("CLAUDE_DIR") or "~/.claude/projects"
    gemini_dir = p.get("GEMINI_DIR") or "~/.gemini/tmp"
    codex_dir = p.get("CODEX_DIR") or "~/.codex"
    mode = normalize_token_mode(p.get("TOKEN_MODE"))

    try:
        today_dim = build_overview_dimension(
            claude_dir=claude_dir, gemini_dir=gemini_dir, codex_dir=codex_dir,
            period="today", mode=mode, language=language,
        )
    except Exception as exc:
        print(f"[daily-overview] scan today failed: {exc}", file=sys.stderr)
        today_dim = {"items": [], "chart": {}, "providerTotals": {}}

    items = today_dim.get("items") or []
    badge = items[0].get("trailingText") if items else None

    provider_icons = {
        "claude": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/claude.png",
        "gemini": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/gemini.png",
        "codex":  "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/openai.png",
    }
    provider_totals = today_dim.get("providerTotals") or {}
    top_prov = max(provider_totals, key=provider_totals.get) if provider_totals else None
    icon_url = provider_icons.get(top_prov) if top_prov and provider_totals.get(top_prov, 0) > 0 else None

    out = {
        "schemaVersion": SCHEMA_VERSION,
        "updatedAt": utc_now_iso(),
        "items": items,
    }
    if badge:
        out["badge"] = badge
    if icon_url:
        out["iconURL"] = icon_url
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
