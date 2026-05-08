#!/usr/bin/env python3
# UsageBoardPlugin:
# {
#   "schemaVersion": 1,
#   "name": "今日总览",
#   "name@zh-Hans": "今日总览",
#   "name@en": "Today Overview",
#   "icon": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/openai.png",
#   "description": "聚合 Claude / Gemini / Codex 当天所有模型的 token 用量",
#   "description@zh-Hans": "聚合 Claude / Gemini / Codex 当天所有模型的 token 用量",
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
#       "name": "CHART_PERIOD",
#       "label": "图表周期",
#       "label@zh-Hans": "图表周期",
#       "label@en": "Chart Period",
#       "type": "choice",
#       "required": false,
#       "defaultValue": "7d",
#       "options": [
#         {"label": "7 天", "label@zh-Hans": "7 天", "label@en": "7 days", "value": "7d"},
#         {"label": "30 天", "label@zh-Hans": "30 天", "label@en": "30 days", "value": "30d"}
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
"""聚合 Claude / Gemini / Codex 三家本地会话的 token 用量。"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
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
    merge_bucket_maps,
    normalize_token_mode,
    parse_params,
    scan_claude,
    scan_codex,
    scan_gemini,
    stat_range,
    tr,
    utc_now_iso,
)


def main() -> int:
    p = parse_params(sys.argv[1:])
    language = lang(p)
    claude_dir = p.get("CLAUDE_DIR") or "~/.claude/projects"
    gemini_dir = p.get("GEMINI_DIR") or "~/.gemini/tmp"
    codex_dir = p.get("CODEX_DIR") or "~/.codex"
    period = (p.get("CHART_PERIOD") or "7d").lower()
    if period not in ("7d", "30d"):
        period = "7d"
    mode = normalize_token_mode(p.get("TOKEN_MODE"))

    _, _, buckets = stat_range(period)
    bucket_set = {bucket_id(b) for b in buckets}
    today_id = bucket_id(buckets[-1])

    by_bucket: dict[str, dict[str, int]] = {b: {} for b in bucket_set}
    by_model_today: dict[str, int] = {}

    # 三家 IO bound 并行，每个 worker 返回独立结果再合并（无共享写）
    def _run(scan_fn, data_dir):
        return scan_fn(data_dir, buckets, mode=mode)

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {
            "claude": ex.submit(_run, scan_claude, claude_dir),
            "gemini": ex.submit(_run, scan_gemini, gemini_dir),
            "codex":  ex.submit(_run, scan_codex,  codex_dir),
        }
        for prov, fut in futures.items():
            try:
                sub_by_bucket, _model_totals = fut.result()
            except Exception as exc:
                print(f"[daily-overview] scan_{prov} failed: {exc}", file=sys.stderr)
                continue
            merge_bucket_maps(by_bucket, sub_by_bucket)
            for m, t in sub_by_bucket.get(today_id, {}).items():
                by_model_today[m] = by_model_today.get(m, 0) + int(t)

    today_total = sum(by_model_today.values())
    sorted_models = sorted(by_model_today.items(), key=lambda kv: -kv[1])

    items = []
    if today_total > 0:
        total_m = round(today_total / 1_000_000, 2)
        items.append({
            "id": "overview-today-total",
            "name": f"{tr(language, 'today_total')}  ▸  {fmt_tokens(today_total, language)} tokens",
            "used": total_m,
            "limit": max(total_m, 0.01),
            "displayStyle": "ratio",
            "resetAt": None,
            "status": "normal",
            "color": "blue",
            "trailingText": fmt_tokens(today_total, language),
        })
        for i, (model, tokens) in enumerate(sorted_models):
            tokens_m = round(tokens / 1_000_000, 2)
            share = tokens / today_total if today_total else 0
            color = "red" if share >= 0.5 else "orange" if share >= 0.25 else "blue"
            items.append({
                "id": f"overview-{i}-{model}",
                "name": f"{model}  ({fmt_tokens(tokens, language)})",
                "used": tokens_m,
                "limit": max(total_m, 0.01),
                "displayStyle": "percent",
                "resetAt": None,
                "status": "normal",
                "color": color,
                "trailingText": fmt_tokens(tokens, language),
            })

    sorted_all_models = sorted(
        {m for v in by_bucket.values() for m in v},
        key=lambda m: -sum(v.get(m, 0) for v in by_bucket.values()),
    )
    chart_buckets = []
    for b in buckets:
        b_id = bucket_id(b)
        segs = [
            {"model": m, "tokens": int(by_bucket.get(b_id, {}).get(m, 0))}
            for m in sorted_all_models if by_bucket.get(b_id, {}).get(m, 0) > 0
        ]
        chart_buckets.append({"id": b_id, "label": bucket_label(b), "segments": segs})
    msg = None if any(b["segments"] for b in chart_buckets) else tr(language, "no_data_today")
    chart = {"kind": "line", "period": period, "bucketUnit": "day",
             "buckets": chart_buckets, "message": msg}

    badge = fmt_tokens(today_total, language) if today_total > 0 else None

    out = {
        "schemaVersion": SCHEMA_VERSION,
        "updatedAt": utc_now_iso(),
        "items": items,
        "chart": chart,
    }
    if badge:
        out["badge"] = badge
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
