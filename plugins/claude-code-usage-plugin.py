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
"""UsageBoard plugin for Claude Code local token usage."""

from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, time, timedelta, timezone
from typing import Any

SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_params(argv: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    i = 0
    while i < len(argv):
        if argv[i] == "--usageboard-param" and i + 1 < len(argv):
            kv = argv[i + 1]
            if "=" in kv:
                k, v = kv.split("=", 1)
                if k:
                    out[k] = v
            i += 2
        else:
            i += 1
    return out


def lang(p: dict[str, str]) -> str:
    return "en" if p.get("USAGEBOARD_LANGUAGE") == "en" else "zh-Hans"


T = {
    "no_data": {"zh-Hans": "暂无可用统计数据", "en": "No stats data available"},
    "total_tokens": {"zh-Hans": "{period} 总用量", "en": "{period} total usage"},
    "scan_failed": {"zh-Hans": "扫描会话失败", "en": "Failed to scan sessions"},
    "period_7d": {"zh-Hans": "7 天", "en": "7d"},
    "period_30d": {"zh-Hans": "30 天", "en": "30d"},
}


def tr(language: str, key: str) -> str:
    return T.get(key, {}).get(language) or T.get(key, {}).get("zh-Hans") or key


def stat_range(period: str):
    now = datetime.now().astimezone()
    days = 7 if period == "7d" else 30
    today = now.date()
    start_date = today - timedelta(days=days - 1)
    start = datetime.combine(start_date, time.min, tzinfo=now.tzinfo)
    end = datetime.combine(today, time.max, tzinfo=now.tzinfo).replace(microsecond=0)
    buckets = [start + timedelta(days=i) for i in range(days)]
    return start, end, buckets


def bucket_id(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def bucket_label(dt: datetime) -> str:
    return dt.strftime("%m-%d")


def aggregate(data_dir: str, buckets: list[datetime]) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    expanded = os.path.expanduser(data_dir)
    files = glob.glob(os.path.join(expanded, "**", "*.jsonl"), recursive=True)

    bucket_set = {bucket_id(b) for b in buckets}
    by_bucket: dict[str, dict[str, int]] = {bid: {} for bid in bucket_set}
    model_totals: dict[str, int] = {}

    for fp in files:
        try:
            with open(fp, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"usage"' not in line or '"assistant"' not in line:
                        continue
                    try:
                        ev = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if ev.get("type") != "assistant":
                        continue
                    msg = ev.get("message")
                    if not isinstance(msg, dict):
                        continue
                    usage = msg.get("usage")
                    if not isinstance(usage, dict):
                        continue
                    model = msg.get("model") or "unknown"

                    tokens = 0
                    for k in ("input_tokens", "output_tokens",
                              "cache_creation_input_tokens", "cache_read_input_tokens"):
                        v = usage.get(k)
                        if isinstance(v, (int, float)):
                            tokens += int(v)
                    if tokens <= 0:
                        continue

                    ts = ev.get("timestamp")
                    if not ts:
                        continue
                    try:
                        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone()
                    except (ValueError, TypeError):
                        continue
                    bid = bucket_id(dt)
                    if bid not in bucket_set:
                        continue
                    by_bucket[bid][model] = by_bucket[bid].get(model, 0) + tokens
                    model_totals[model] = model_totals.get(model, 0) + tokens
        except (OSError, UnicodeDecodeError):
            continue

    return by_bucket, model_totals


def build_chart(by_bucket: dict[str, dict[str, int]], model_totals: dict[str, int],
                buckets: list[datetime], period: str, language: str) -> dict[str, Any]:
    sorted_models = [m for m, _ in sorted(model_totals.items(), key=lambda x: -x[1])]
    chart_buckets = []
    for b in buckets:
        bid = bucket_id(b)
        segs = [
            {"model": m, "tokens": int(by_bucket[bid].get(m, 0))}
            for m in sorted_models if by_bucket[bid].get(m, 0) > 0
        ]
        chart_buckets.append({"id": bid, "label": bucket_label(b), "segments": segs})
    msg = None
    if not any(b["segments"] for b in chart_buckets):
        msg = tr(language, "no_data")
    return {"kind": "line", "period": period, "bucketUnit": "day",
            "buckets": chart_buckets, "message": msg}


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def main() -> int:
    p = parse_params(sys.argv[1:])
    language = lang(p)
    data_dir = p.get("DATA_DIR", "") or "~/.claude/projects"
    period = p.get("STAT_PERIOD", "7d").lower()
    if period not in ("7d", "30d"):
        period = "7d"

    period_label = tr(language, "period_7d" if period == "7d" else "period_30d")

    try:
        _, _, buckets = stat_range(period)
        by_bucket, model_totals = aggregate(data_dir, buckets)
    except Exception:
        result = {
            "schemaVersion": SCHEMA_VERSION,
            "updatedAt": utc_now_iso(),
            "items": [{
                "id": "claude-error",
                "name": tr(language, "scan_failed"),
                "used": 0, "limit": 1, "displayStyle": "percent",
                "resetAt": None, "status": "critical",
            }],
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0

    total = int(sum(model_totals.values()))
    today_id = bucket_id(buckets[-1])
    today_total = sum(by_bucket.get(today_id, {}).values())
    peak_total = max((sum(v.values()) for v in by_bucket.values()), default=0)
    today_m = round(today_total / 1_000_000, 2)
    peak_m = round(peak_total / 1_000_000, 2)
    ratio = (today_total / peak_total) if peak_total > 0 else 0
    status = "critical" if ratio >= 1.0 else "warning" if ratio >= 0.8 else "normal"
    color = "red" if ratio >= 1.0 else "orange" if ratio >= 0.8 else "blue"

    items = [{
        "id": "claude-total",
        "name": f"{period_label}: {fmt_tokens(total)} tokens",
        "used": today_m,
        "limit": max(peak_m, 0.01),
        "displayStyle": "ratio",
        "resetAt": None,
        "status": status,
        "color": color,
    }]

    chart = build_chart(by_bucket, model_totals, buckets, period, language)

    print(json.dumps({
        "schemaVersion": SCHEMA_VERSION,
        "updatedAt": utc_now_iso(),
        "items": items,
        "chart": chart,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
