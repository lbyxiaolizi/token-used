#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "用量总览",
#   "name@zh-Hans": "用量总览",
#   "name@en": "Usage Overview",
#   "icon": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/openai.png",
#   "description": "聚合 Claude / Gemini / Codex 各时段的 token 用量（面板内可切今日 / 7d / 30d / 90d / 全部）",
#   "description@zh-Hans": "聚合 Claude / Gemini / Codex 各时段的 token 用量（面板内可切今日 / 7d / 30d / 90d / 全部）",
#   "description@en": "Aggregate Claude / Gemini / Codex token usage across periods (in-panel switch: today / 7d / 30d / 90d / all)",
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
#       "name": "CHART_PERIOD",
#       "label": "默认图表周期",
#       "label@zh-Hans": "默认图表周期",
#       "label@en": "Default Chart Period",
#       "type": "choice",
#       "required": false,
#       "defaultValue": "30d",
#       "options": [
#         {"label": "今日", "label@zh-Hans": "今日", "label@en": "Today", "value": "today"},
#         {"label": "7 天", "label@zh-Hans": "7 天", "label@en": "7 days", "value": "7d"},
#         {"label": "30 天", "label@zh-Hans": "30 天", "label@en": "30 days", "value": "30d"},
#         {"label": "90 天", "label@zh-Hans": "90 天", "label@en": "90 days", "value": "90d"},
#         {"label": "全部 (12 月)", "label@zh-Hans": "全部 (12 月)", "label@en": "All (12 mo)", "value": "all"}
#       ]
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
"""聚合 Claude / Gemini / Codex 三家本地会话的 token 用量（多 period 维度）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from _shared import (  # noqa: E402
    PERIODS,
    SCHEMA_VERSION,
    build_overview_dimension,
    fmt_tokens,
    lang,
    normalize_period,
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
    default_period = normalize_period(p.get("CHART_PERIOD"))
    mode = normalize_token_mode(p.get("TOKEN_MODE"))

    dims: dict[str, dict] = {}
    for period in PERIODS:
        try:
            dims[period] = build_overview_dimension(
                claude_dir=claude_dir, gemini_dir=gemini_dir, codex_dir=codex_dir,
                period=period, mode=mode, language=language,
            )
        except Exception as exc:
            print(f"[daily-overview] dim {period} failed: {exc}", file=sys.stderr)
            dims[period] = {"label": period, "bucketUnit": "day", "items": [], "chart": {}}

    if default_period not in dims:
        default_period = next(iter(dims))
    default_dim = dims[default_period]

    # badge：取当前 default dimension 的 hero trailingText，跟用户首次看到的数字一致
    default_items = default_dim.get("items") or []
    badge = default_items[0].get("trailingText") if default_items else None

    out = {
        "schemaVersion": SCHEMA_VERSION,
        "updatedAt": utc_now_iso(),
        "items": default_dim.get("items", []),
        "chart": default_dim.get("chart", {}),
        "defaultDimension": default_period,
        "dimensionOrder": list(PERIODS),
        "dimensions": dims,
    }
    if badge:
        out["badge"] = badge
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
