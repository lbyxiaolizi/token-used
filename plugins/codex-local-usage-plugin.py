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
#       "label": "统计周期",
#       "label@zh-Hans": "统计周期",
#       "label@en": "Stats Period",
#       "type": "choice",
#       "required": false,
#       "defaultValue": "7d",
#       "options": [
#         {"label": "7 天", "label@zh-Hans": "7 天", "label@en": "7 days", "value": "7d"},
#         {"label": "30 天", "label@zh-Hans": "30 天", "label@en": "30 days", "value": "30d"}
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
    SCHEMA_VERSION,
    bucket_id,
    bucket_label,
    fmt_tokens,
    lang,
    parse_params,
    scan_codex,
    stat_range,
    tr,
    utc_now_iso,
)


def main() -> int:
    p = parse_params(sys.argv[1:])
    language = lang(p)
    data_dir = p.get("DATA_DIR") or "~/.codex"
    period = (p.get("STAT_PERIOD") or "7d").lower()
    if period not in ("7d", "30d"):
        period = "7d"
    period_label = tr(language, "period_7d" if period == "7d" else "period_30d")

    try:
        _, _, buckets = stat_range(period)
        by_bucket, model_totals = scan_codex(data_dir, buckets)
    except Exception as exc:
        print(f"[codex-local-usage-plugin] scan failed: {exc}", file=sys.stderr)
        print(json.dumps({
            "schemaVersion": SCHEMA_VERSION,
            "updatedAt": utc_now_iso(),
            "items": [{
                "id": "codex-error",
                "name": tr(language, "scan_failed"),
                "used": 0, "limit": 1, "displayStyle": "percent",
                "resetAt": None, "status": "critical",
            }],
        }, ensure_ascii=False))
        return 0

    total = int(sum(model_totals.values()))
    today_id = bucket_id(buckets[-1])
    today_total = int(sum(by_bucket.get(today_id, {}).values()))
    peak_total = int(max((sum(v.values()) for v in by_bucket.values()), default=0))
    today_m = round(today_total / 1_000_000, 2)
    peak_m = round(peak_total / 1_000_000, 2)
    ratio = (today_total / peak_total) if peak_total > 0 else 0
    status = "critical" if ratio >= 1.0 else "warning" if ratio >= 0.8 else "normal"
    color = "red" if ratio >= 1.0 else "orange" if ratio >= 0.8 else "blue"

    items = []
    if total > 0:
        items.append({
            "id": "codex-total",
            "name": f"{period_label}: {fmt_tokens(total, language)} tokens",
            "used": today_m,
            "limit": max(peak_m, 0.01),
            "displayStyle": "ratio",
            "resetAt": None,
            "status": status,
            "color": color,
            "trailingText": fmt_tokens(today_total, language),
        })

    sorted_models = [m for m, _ in sorted(model_totals.items(), key=lambda x: -x[1])]
    chart_buckets = []
    for b in buckets:
        bid = bucket_id(b)
        segs = [
            {"model": m, "tokens": int(by_bucket.get(bid, {}).get(m, 0))}
            for m in sorted_models if by_bucket.get(bid, {}).get(m, 0) > 0
        ]
        chart_buckets.append({"id": bid, "label": bucket_label(b), "segments": segs})
    msg = None if any(b["segments"] for b in chart_buckets) else tr(language, "no_data")
    chart = {"kind": "line", "period": period, "bucketUnit": "day",
             "buckets": chart_buckets, "message": msg}

    print(json.dumps({
        "schemaVersion": SCHEMA_VERSION,
        "updatedAt": utc_now_iso(),
        "items": items,
        "chart": chart,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
