#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "Claude Code",
#   "name@zh-Hans": "Claude Code",
#   "name@en": "Claude Code",
#   "icon": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/claude-color.png",
#   "description": "查询 Claude Code 本地会话的 token 用量统计",
#   "description@zh-Hans": "查询 Claude Code 本地会话的 token 用量统计",
#   "description@en": "Aggregate Claude Code local session token usage",
#   "parameters": [
#     {
#       "name": "DATA_DIR",
#       "label": "数据目录",
#       "label@zh-Hans": "数据目录",
#       "label@en": "Data Directory",
#       "type": "string",
#       "required": false,
#       "defaultValue": "~/.claude/projects",
#       "placeholder": "~/.claude/projects"
#     },
#     {
#       "name": "STAT_PERIOD",
#       "label": "默认统计周期",
#       "label@zh-Hans": "默认统计周期",
#       "label@en": "Default Stats Period",
#       "type": "choice",
#       "required": false,
#       "defaultValue": "30d",
#       "options": [
#         {"label": "7 天", "label@zh-Hans": "7 天", "label@en": "7 days", "value": "7d"},
#         {"label": "30 天", "label@zh-Hans": "30 天", "label@en": "30 days", "value": "30d"},
#         {"label": "90 天", "label@zh-Hans": "90 天", "label@en": "90 days", "value": "90d"},
#         {"label": "全部 (12 月)", "label@zh-Hans": "全部 (12 月)", "label@en": "All (12 mo)", "value": "all"}
#       ]
#     },
#     {
#       "name": "TOKEN_MODE",
#       "label": "Token 计算口径",
#       "label@zh-Hans": "Token 计算口径",
#       "label@en": "Token Counting Mode",
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
"""UsageBoard plugin for Claude Code local token usage."""
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
    build_per_cli_dimension,
    lang,
    normalize_period,
    normalize_token_mode,
    parse_params,
    scan_claude,
    tr,
    utc_now_iso,
)


def main() -> int:
    p = parse_params(sys.argv[1:])
    language = lang(p)
    data_dir = p.get("DATA_DIR") or "~/.claude/projects"
    default_period = normalize_period(p.get("STAT_PERIOD"))
    mode = normalize_token_mode(p.get("TOKEN_MODE"))

    dims: dict[str, dict] = {}
    for period in PERIODS:
        try:
            dims[period] = build_per_cli_dimension(
                scan_fn=scan_claude, data_dir=data_dir,
                period=period, mode=mode, language=language,
                hero_id_prefix="claude",
            )
        except Exception as exc:
            print(f"[claude-code-usage-plugin] dim {period} failed: {exc}", file=sys.stderr)
            dims[period] = {"label": period, "bucketUnit": "day", "items": [], "chart": {}}

    if default_period not in dims:
        default_period = next(iter(dims))
    default_dim = dims[default_period]

    out = {
        "schemaVersion": SCHEMA_VERSION,
        "updatedAt": utc_now_iso(),
        "items": default_dim.get("items", []),
        "chart": default_dim.get("chart", {}),
        "defaultDimension": default_period,
        "dimensionOrder": list(PERIODS),
        "dimensions": dims,
    }
    # 注意：所有 dimension 都没数据时保留 items=[]，让宿主 visiblePlugins 自动隐藏整个 panel
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
