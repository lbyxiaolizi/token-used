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
#     }
#   ]
# }
# /UsageBoardPlugin
"""聚合 Claude / Gemini / Codex 三家本地会话的 token 用量。"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

SCHEMA_VERSION = 1
_CODEX_FILENAME_DATE = re.compile(r"rollout-(\d{4}-\d{2}-\d{2})T")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_params(argv):
    out = {}
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


def lang(p):
    return "en" if p.get("USAGEBOARD_LANGUAGE") == "en" else "zh-Hans"


T = {
    "no_data_today": {"zh-Hans": "今日暂无用量", "en": "No usage today"},
    "today_total": {"zh-Hans": "今日合计", "en": "Today total"},
}


def tr(language, key):
    return T.get(key, {}).get(language) or T.get(key, {}).get("zh-Hans") or key


def chart_range(period):
    now = datetime.now().astimezone()
    days = 7 if period == "7d" else 30
    today = now.date()
    start_date = today - timedelta(days=days - 1)
    start = datetime.combine(start_date, time.min, tzinfo=now.tzinfo)
    buckets = [start + timedelta(days=i) for i in range(days)]
    return start, buckets


def bid(dt):
    return dt.strftime("%Y-%m-%d") if isinstance(dt, datetime) else dt.strftime("%Y-%m-%d")


def blabel(dt):
    return dt.strftime("%m-%d")


def parse_iso(ts: Any):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone()
    except (ValueError, TypeError):
        return None


# ---------- Claude ----------

def scan_claude(data_dir: str, today_id: str, by_bucket: dict[str, dict[str, int]],
                bucket_set: set[str], by_model_today: dict[str, int]):
    expanded = os.path.expanduser(data_dir)
    files = glob.glob(os.path.join(expanded, "**", "*.jsonl"), recursive=True)
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
                    model = msg.get("model") or "claude-unknown"
                    tokens = 0
                    for k in ("input_tokens", "output_tokens",
                              "cache_creation_input_tokens", "cache_read_input_tokens"):
                        v = usage.get(k)
                        if isinstance(v, (int, float)):
                            tokens += int(v)
                    if tokens <= 0:
                        continue
                    dt = parse_iso(ev.get("timestamp"))
                    if not dt:
                        continue
                    b = bid(dt)
                    if b in bucket_set:
                        by_bucket.setdefault(b, {})[model] = by_bucket[b].get(model, 0) + tokens
                    if b == today_id:
                        by_model_today[model] = by_model_today.get(model, 0) + tokens
        except (OSError, UnicodeDecodeError):
            continue


# ---------- Gemini ----------

def scan_gemini(data_dir: str, today_id: str, by_bucket, bucket_set, by_model_today):
    expanded = os.path.expanduser(data_dir)
    files = glob.glob(os.path.join(expanded, "**", "session-*.json"), recursive=True)
    for fp in files:
        try:
            with open(fp, encoding="utf-8", errors="replace") as fh:
                doc = json.load(fh)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            continue
        msgs = doc.get("messages") if isinstance(doc, dict) else None
        if not isinstance(msgs, list):
            continue
        for m in msgs:
            if not isinstance(m, dict):
                continue
            tokens = m.get("tokens")
            if not isinstance(tokens, dict):
                continue
            total = tokens.get("total")
            if not isinstance(total, (int, float)):
                total = 0
                for k in ("input", "output", "cached", "thoughts", "tool"):
                    v = tokens.get(k)
                    if isinstance(v, (int, float)):
                        total += int(v)
            total = int(total)
            if total <= 0:
                continue
            model = m.get("model") or "gemini-unknown"
            dt = parse_iso(m.get("timestamp"))
            if not dt:
                continue
            b = bid(dt)
            if b in bucket_set:
                by_bucket.setdefault(b, {})[model] = by_bucket[b].get(model, 0) + total
            if b == today_id:
                by_model_today[model] = by_model_today.get(model, 0) + total


# ---------- Codex ----------

def scan_codex(data_dir: str, today_id: str, by_bucket, bucket_set, by_model_today,
               start_date: date):
    expanded = os.path.expanduser(data_dir)
    files = []
    for pat in (
        os.path.join(expanded, "sessions", "**", "*.jsonl"),
        os.path.join(expanded, "archived_sessions", "*.jsonl"),
    ):
        files.extend(glob.glob(pat, recursive=True))
    s = start_date.strftime("%Y-%m-%d")
    today = date.today().strftime("%Y-%m-%d")
    relevant = []
    for f in files:
        m = _CODEX_FILENAME_DATE.search(os.path.basename(f))
        if m:
            d = m.group(1)
            if s <= d <= today:
                relevant.append(f)
        else:
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(f)).date().strftime("%Y-%m-%d")
                if s <= mtime <= today:
                    relevant.append(f)
            except OSError:
                pass

    for fp in relevant:
        current_model = None
        prev_total = 0.0
        first = True
        try:
            with open(fp, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"turn_context"' not in line and '"token_count"' not in line:
                        continue
                    try:
                        ev = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    payload = ev.get("payload")
                    if not isinstance(payload, dict):
                        continue
                    if ev.get("type") == "turn_context":
                        m = payload.get("model")
                        if isinstance(m, str) and m.strip():
                            current_model = m.strip()
                    if payload.get("type") == "token_count":
                        info = payload.get("info")
                        if not isinstance(info, dict):
                            continue
                        tot = info.get("total_token_usage")
                        if not isinstance(tot, dict):
                            continue
                        total_tokens = tot.get("total_tokens")
                        if not isinstance(total_tokens, (int, float)):
                            continue
                        total_tokens = float(total_tokens)
                        delta = total_tokens if first else max(total_tokens - prev_total, 0)
                        prev_total = total_tokens
                        first = False
                        if delta <= 0:
                            continue
                        model = current_model or "codex-unknown"
                        dt = parse_iso(payload.get("timestamp") or ev.get("timestamp"))
                        if not dt:
                            continue
                        b = bid(dt)
                        if b in bucket_set:
                            by_bucket.setdefault(b, {})[model] = by_bucket[b].get(model, 0) + delta
                        if b == today_id:
                            by_model_today[model] = by_model_today.get(model, 0) + int(delta)
        except (OSError, UnicodeDecodeError):
            continue


# ---------- Output ----------

def fmt_tokens(n):
    n = int(n)
    if n >= 1_000_000_000: return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:     return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:         return f"{n / 1_000:.1f}k"
    return str(n)


def main() -> int:
    p = parse_params(sys.argv[1:])
    language = lang(p)
    claude_dir = p.get("CLAUDE_DIR") or "~/.claude/projects"
    gemini_dir = p.get("GEMINI_DIR") or "~/.gemini/tmp"
    codex_dir = p.get("CODEX_DIR") or "~/.codex"
    period = (p.get("CHART_PERIOD") or "7d").lower()
    if period not in ("7d", "30d"):
        period = "7d"

    start, buckets = chart_range(period)
    bucket_set = {bid(b) for b in buckets}
    today_id = bid(buckets[-1])

    by_bucket: dict[str, dict[str, int]] = {b: {} for b in bucket_set}
    by_model_today: dict[str, int] = {}

    try:
        scan_claude(claude_dir, today_id, by_bucket, bucket_set, by_model_today)
    except Exception:
        pass
    try:
        scan_gemini(gemini_dir, today_id, by_bucket, bucket_set, by_model_today)
    except Exception:
        pass
    try:
        scan_codex(codex_dir, today_id, by_bucket, bucket_set, by_model_today, start.date())
    except Exception:
        pass

    today_total = sum(by_model_today.values())
    sorted_models = sorted(by_model_today.items(), key=lambda kv: -kv[1])

    items = []
    if today_total > 0:
        total_m = round(today_total / 1_000_000, 2)
        # Hero 汇总条：标题就是大数字，进度条 100% 满
        items.append({
            "id": "overview-today-total",
            "name": f"今日合计  ▸  {fmt_tokens(today_total)} tokens",
            "used": total_m,
            "limit": max(total_m, 0.01),
            "displayStyle": "ratio",
            "resetAt": None,
            "status": "normal",
            "color": "blue",
        })
        # 每个模型一条 item，limit = 今日总量 → 进度条 = 该模型今天的占比
        for i, (model, tokens) in enumerate(sorted_models):
            tokens_m = round(tokens / 1_000_000, 2)
            share = tokens / today_total
            color = "red" if share >= 0.5 else "orange" if share >= 0.25 else "blue"
            items.append({
                "id": f"overview-{i}-{model}",
                "name": f"{model}  ({fmt_tokens(tokens)})",
                "used": tokens_m,
                "limit": max(total_m, 0.01),
                "displayStyle": "percent",
                "resetAt": None,
                "status": "normal",
                "color": color,
            })

    # 跨源图表：每天按模型分段
    sorted_all_models = sorted(
        {m for v in by_bucket.values() for m in v},
        key=lambda m: -sum(v.get(m, 0) for v in by_bucket.values())
    )
    chart_buckets = []
    for b in buckets:
        b_id = bid(b)
        segs = [
            {"model": m, "tokens": int(by_bucket.get(b_id, {}).get(m, 0))}
            for m in sorted_all_models if by_bucket.get(b_id, {}).get(m, 0) > 0
        ]
        chart_buckets.append({"id": b_id, "label": blabel(b), "segments": segs})
    msg = None if any(b["segments"] for b in chart_buckets) else tr(language, "no_data_today")
    chart = {"kind": "line", "period": period, "bucketUnit": "day",
             "buckets": chart_buckets, "message": msg}

    badge = fmt_tokens(today_total) if today_total > 0 else None

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
