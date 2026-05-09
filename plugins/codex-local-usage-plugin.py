#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "Codex (本地)",
#   "name@zh-Hans": "Codex (本地)",
#   "name@en": "Codex (Local)",
#   "icon": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/codex-color.png",
#   "description": "查询 Codex CLI 本地会话的 token 用量统计(不依赖 ChatGPT 订阅)",
#   "description@zh-Hans": "查询 Codex CLI 本地会话的 token 用量统计(不依赖 ChatGPT 订阅)",
#   "description@en": "Aggregate Codex CLI local session token usage (no ChatGPT subscription needed)",
#   "parameters": [
#     {
#       "name": "DATA_DIR",
#       "label": "数据目录",
#       "label@zh-Hans": "数据目录",
#       "label@en": "Data Directory",
#       "type": "string",
#       "required": false,
#       "defaultValue": "~/.codex",
#       "placeholder": "~/.codex"
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
#         {"label": "今日", "label@zh-Hans": "今日", "label@en": "Today", "value": "today"},
#         {"label": "7 天", "label@zh-Hans": "7 天", "label@en": "7 days", "value": "7d"},
#         {"label": "30 天", "label@zh-Hans": "30 天", "label@en": "30 days", "value": "30d"},
#         {"label": "90 天", "label@zh-Hans": "90 天", "label@en": "90 days", "value": "90d"},
#         {"label": "全部 (12 月)", "label@zh-Hans": "全部 (12 月)", "label@en": "All (12 mo)", "value": "all"}
#       ]
#     }
#   ]
# }
# /UsageBoardPlugin
"""UsageBoard plugin for Codex CLI local token usage (API-key mode)."""
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
    parse_params,
    scan_codex,
    tr,
    utc_now_iso,
)


def main() -> int:
    p = parse_params(sys.argv[1:])
    language = lang(p)
    data_dir = p.get("DATA_DIR") or "~/.codex"
    default_period = normalize_period(p.get("STAT_PERIOD"))

    dims: dict[str, dict] = {}
    for period in PERIODS:
        try:
            dims[period] = build_per_cli_dimension(
                scan_fn=scan_codex, data_dir=data_dir,
                period=period, mode="billable", language=language,
                hero_id_prefix="codex",
            )
        except Exception as exc:
            print(f"[codex-local-usage-plugin] dim {period} failed: {exc}", file=sys.stderr)
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
    # 全 dimension 空 → items=[]，宿主 visiblePlugins 会自动隐藏整个 panel
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
