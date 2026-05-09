"""Provider parsers, file enumeration, and scan helpers for TokenUsed."""
from __future__ import annotations

import glob
import json
import os
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path

from _shared_cache import aggregate_with_cache
from _shared_core import (
    DEFAULT_TOKEN_MODE,
    PARSER_VERSIONS,
    bucket_id,
    mtime_within,
    normalize_period,
    parse_iso,
    period_chart_buckets,
    period_window,
)

_CLAUDE_KEYS_RAW = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)
_CLAUDE_KEYS_BILLABLE = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
)


def _bump(bag: dict[str, dict[str, int]], model: str, raw: int, billable: int) -> None:
    cur = bag.get(model)
    if cur is None:
        bag[model] = {"raw": int(raw), "billable": int(billable)}
    else:
        cur["raw"] = int(cur.get("raw", 0)) + int(raw)
        cur["billable"] = int(cur.get("billable", 0)) + int(billable)


def parse_claude_file(fp: str) -> dict[str, dict[str, dict[str, int]]]:
    out: dict[str, dict[str, dict[str, int]]] = {}
    try:
        with open(fp, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    ev = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(ev, dict) or ev.get("type") != "assistant":
                    continue
                msg = ev.get("message")
                if not isinstance(msg, dict):
                    continue
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue
                raw = 0
                billable = 0
                for k in _CLAUDE_KEYS_RAW:
                    v = usage.get(k)
                    if isinstance(v, (int, float)):
                        raw += int(v)
                for k in _CLAUDE_KEYS_BILLABLE:
                    v = usage.get(k)
                    if isinstance(v, (int, float)):
                        billable += int(v)
                if raw <= 0 and billable <= 0:
                    continue
                dt = parse_iso(ev.get("timestamp"))
                if not dt:
                    continue
                b = bucket_id(dt)
                model = msg.get("model") or "claude-unknown"
                _bump(out.setdefault(b, {}), model, raw, billable)
    except (OSError, UnicodeDecodeError):
        return out
    return out


def parse_gemini_file(fp: str) -> dict[str, dict[str, dict[str, int]]]:
    out: dict[str, dict[str, dict[str, int]]] = {}
    try:
        with open(fp, encoding="utf-8", errors="replace") as fh:
            doc = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return out
    msgs = doc.get("messages") if isinstance(doc, dict) else None
    if not isinstance(msgs, list):
        return out
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
        b = bucket_id(dt)
        _bump(out.setdefault(b, {}), model, raw=total, billable=total)
    return out


def parse_codex_file(fp: str) -> dict[str, dict[str, dict[str, int]]]:
    out: dict[str, dict[str, dict[str, int]]] = {}
    current_model: str | None = None
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
                if not isinstance(ev, dict):
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
                    b = bucket_id(dt)
                    di = int(delta)
                    _bump(out.setdefault(b, {}), model, raw=di, billable=di)
    except (OSError, UnicodeDecodeError):
        return out
    return out


_CODEX_FILENAME_DATE = re.compile(r"rollout-(\d{4}-\d{2}-\d{2})T")


def _period_mtime_cutoff(period: str, *, today: date | None = None) -> float:
    start_d, _ = period_window(period, today=today)
    return (datetime.combine(start_d, time.min).astimezone()
            - timedelta(days=2)).timestamp()


def list_claude_files(data_dir: str, cutoff_ts: float) -> list[str]:
    expanded = os.path.expanduser(data_dir)
    files = glob.glob(os.path.join(expanded, "**", "*.jsonl"), recursive=True)
    return [f for f in files if mtime_within(f, cutoff_ts)]


def list_gemini_files(data_dir: str, cutoff_ts: float) -> list[str]:
    expanded = os.path.expanduser(data_dir)
    files = glob.glob(os.path.join(expanded, "**", "session-*.json"), recursive=True)
    return [f for f in files if mtime_within(f, cutoff_ts)]


def list_codex_files(data_dir: str, start_date: date) -> list[str]:
    expanded = os.path.expanduser(data_dir)
    files: list[str] = []
    for pat in (
        os.path.join(expanded, "sessions", "**", "*.jsonl"),
        os.path.join(expanded, "archived_sessions", "*.jsonl"),
    ):
        files.extend(glob.glob(pat, recursive=True))
    s = start_date.strftime("%Y-%m-%d")
    today = date.today().strftime("%Y-%m-%d")
    out: list[str] = []
    for f in files:
        m = _CODEX_FILENAME_DATE.search(os.path.basename(f))
        if m:
            d = m.group(1)
            if s <= d <= today:
                out.append(f)
        else:
            try:
                mt = datetime.fromtimestamp(os.path.getmtime(f)).date().strftime("%Y-%m-%d")
                if s <= mt <= today:
                    out.append(f)
            except OSError:
                pass
    return out


def scan_claude(data_dir: str, period: str, *,
                mode: str = DEFAULT_TOKEN_MODE, cache_root: Path | None = None
                ) -> tuple[dict[str, dict[str, int]], dict[str, int], list[dict[str, str]], str]:
    period = normalize_period(period)
    today = datetime.now().astimezone().date()
    cutoff = _period_mtime_cutoff(period, today=today)
    files = list_claude_files(data_dir, cutoff)
    chart_meta, unit = period_chart_buckets(period, today=today)
    by_bucket, model_totals = aggregate_with_cache(
        provider="claude", data_dir=data_dir,
        files=files, parse_file=parse_claude_file,
        parser_version=PARSER_VERSIONS["claude"],
        bucket_set={b["id"] for b in chart_meta},
        mode=mode, bucket_unit=unit, cache_root=cache_root,
    )
    return by_bucket, model_totals, chart_meta, unit


def scan_gemini(data_dir: str, period: str, *,
                mode: str = DEFAULT_TOKEN_MODE, cache_root: Path | None = None
                ) -> tuple[dict[str, dict[str, int]], dict[str, int], list[dict[str, str]], str]:
    period = normalize_period(period)
    today = datetime.now().astimezone().date()
    cutoff = _period_mtime_cutoff(period, today=today)
    files = list_gemini_files(data_dir, cutoff)
    chart_meta, unit = period_chart_buckets(period, today=today)
    by_bucket, model_totals = aggregate_with_cache(
        provider="gemini", data_dir=data_dir,
        files=files, parse_file=parse_gemini_file,
        parser_version=PARSER_VERSIONS["gemini"],
        bucket_set={b["id"] for b in chart_meta},
        mode=mode, bucket_unit=unit, cache_root=cache_root,
    )
    return by_bucket, model_totals, chart_meta, unit


def scan_codex(data_dir: str, period: str, *,
               mode: str = DEFAULT_TOKEN_MODE, cache_root: Path | None = None
               ) -> tuple[dict[str, dict[str, int]], dict[str, int], list[dict[str, str]], str]:
    period = normalize_period(period)
    today = datetime.now().astimezone().date()
    start_d, _ = period_window(period, today=today)
    files = list_codex_files(data_dir, start_d)
    chart_meta, unit = period_chart_buckets(period, today=today)
    by_bucket, model_totals = aggregate_with_cache(
        provider="codex", data_dir=data_dir,
        files=files, parse_file=parse_codex_file,
        parser_version=PARSER_VERSIONS["codex"],
        bucket_set={b["id"] for b in chart_meta},
        mode=mode, bucket_unit=unit, cache_root=cache_root,
    )
    return by_bucket, model_totals, chart_meta, unit
