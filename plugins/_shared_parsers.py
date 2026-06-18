"""Provider parsers, file enumeration, and scan helpers for TokenUsed."""
from __future__ import annotations

import glob
import json
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from _shared_cache import (
    aggregate_with_cache,
    cache_file_path,
    file_fingerprint,
    load_cache,
    save_cache_atomic,
    with_cache_lock,
)
from _shared_core import (
    CACHE_VERSION,
    DEFAULT_TOKEN_MODE,
    PARSER_VERSIONS,
    SCHEMA_VERSION,
    bucket_id,
    bucket_id_for_date,
    current_tz_offset_seconds,
    mtime_within,
    normalize_token_mode,
    normalize_period,
    parse_iso,
    period_chart_buckets,
    period_window,
    utc_now_iso,
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
    seen_messages: dict[str, tuple[int, int, datetime, str]] = {}
    try:
        with open(fp, encoding="utf-8", errors="replace") as fh:
            for line_no, line in enumerate(fh, start=1):
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
                model = msg.get("model") or "claude-unknown"
                msg_id = msg.get("id")
                if isinstance(msg_id, str) and msg_id.strip():
                    msg_key = msg_id.strip()
                else:
                    msg_key = f"__line__:{line_no}"
                prev = seen_messages.get(msg_key)
                if (prev is None
                        or (raw + billable, raw, billable)
                        > (prev[0] + prev[1], prev[0], prev[1])):
                    seen_messages[msg_key] = (raw, billable, dt, model)
    except (OSError, UnicodeDecodeError):
        return out
    for raw, billable, dt, model in seen_messages.values():
        b = bucket_id(dt)
        _bump(out.setdefault(b, {}), model, raw, billable)
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


def _codex_usage_total(usage: object) -> int | None:
    if not isinstance(usage, dict):
        return None
    total_tokens = usage.get("total_tokens")
    if isinstance(total_tokens, (int, float)) and not isinstance(total_tokens, bool):
        total = int(total_tokens)
        return total if total >= 0 else None
    total = 0
    found = False
    for k in ("input_tokens", "cached_input_tokens", "output_tokens",
              "reasoning_output_tokens"):
        v = usage.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            total += int(v)
            found = True
    return total if found and total >= 0 else None


def _read_codex_file(fp: str) -> tuple[str, list[tuple[datetime, int, str, int]]]:
    events: list[tuple[datetime, int, str, int]] = []
    session_id: str | None = None
    current_model: str | None = None
    seq = 0
    try:
        with open(fp, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if ("session_meta" not in line
                        and "turn_context" not in line
                        and "token_count" not in line):
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

                ev_type = ev.get("type")
                payload_type = payload.get("type")
                if ev_type == "session_meta" or payload_type == "session_meta":
                    sid = payload.get("id") or payload.get("session_id") or ev.get("session_id")
                    if isinstance(sid, str) and sid.strip():
                        session_id = sid.strip()
                    m = payload.get("model")
                    if isinstance(m, str) and m.strip():
                        current_model = m.strip()
                    continue

                if ev_type == "turn_context" or payload_type == "turn_context":
                    m = payload.get("model")
                    if isinstance(m, str) and m.strip():
                        current_model = m.strip()
                    continue

                if ev_type != "token_count" and payload_type != "token_count":
                    continue
                info = payload.get("info")
                if not isinstance(info, dict):
                    continue
                total = _codex_usage_total(info.get("total_token_usage"))
                if total is None:
                    continue
                dt = parse_iso(payload.get("timestamp") or ev.get("timestamp"))
                if not dt:
                    continue
                seq += 1
                model = current_model or "codex-unknown"
                events.append((dt, seq, model, total))
    except (OSError, UnicodeDecodeError):
        return os.path.realpath(fp), []
    return session_id or os.path.realpath(fp), events


_CODEX_EVENT_CACHE_PROVIDER = "codex-events"


def _encode_codex_events(events: list[tuple[datetime, int, str, int]]) -> list[dict[str, Any]]:
    return [
        {"timestamp": dt.isoformat(), "seq": int(seq), "model": model, "total": int(total)}
        for dt, seq, model, total in events
    ]


def _decode_codex_events(raw: object) -> list[tuple[datetime, int, str, int]] | None:
    if not isinstance(raw, list):
        return None
    out: list[tuple[datetime, int, str, int]] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        dt = parse_iso(item.get("timestamp"))
        seq = item.get("seq")
        model = item.get("model")
        total = item.get("total")
        if dt is None:
            return None
        if not (isinstance(seq, int) and not isinstance(seq, bool) and seq > 0):
            return None
        if not (isinstance(model, str) and model.strip()):
            return None
        if not (isinstance(total, int) and not isinstance(total, bool) and total >= 0):
            return None
        out.append((dt, seq, model.strip(), total))
    return out


def _empty_codex_event_cache(data_dir: str, parser_version: str,
                             tz_offset: int) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "cacheVersion": CACHE_VERSION,
        "provider": _CODEX_EVENT_CACHE_PROVIDER,
        "dataDir": data_dir,
        "parserVersion": parser_version,
        "tzOffsetSeconds": tz_offset,
        "updatedAt": utc_now_iso(),
        "files": {},
    }


def _codex_event_cache_invalid(cache: dict[str, Any], data_dir: str,
                               parser_version: str, tz_offset: int) -> bool:
    if cache.get("cacheVersion") != CACHE_VERSION:
        return True
    if cache.get("provider") != _CODEX_EVENT_CACHE_PROVIDER:
        return True
    if cache.get("parserVersion") != parser_version:
        return True
    if cache.get("dataDir") != data_dir:
        return True
    raw_tz = cache.get("tzOffsetSeconds")
    if not isinstance(raw_tz, (int, float)) or int(raw_tz) != tz_offset:
        return True
    return False


def _decode_codex_cache_entry(entry: object, fingerprint: dict[str, int]
                              ) -> tuple[str, list[tuple[datetime, int, str, int]]] | None:
    if not isinstance(entry, dict):
        return None
    if entry.get("fingerprint") != fingerprint:
        return None
    session_id = entry.get("sessionId")
    if not (isinstance(session_id, str) and session_id):
        return None
    events = _decode_codex_events(entry.get("events"))
    if events is None:
        return None
    return session_id, events


def _read_codex_files(files: list[str], *, data_dir: str | None = None,
                      cache_root: Path | None = None
                      ) -> list[tuple[str, list[tuple[datetime, int, str, int]]]]:
    file_list = sorted(os.path.realpath(fp) for fp in files)
    if data_dir is None:
        return [_read_codex_file(fp) for fp in file_list]

    expanded_dir = os.path.realpath(os.path.expanduser(data_dir))
    parser_version = PARSER_VERSIONS["codex"]
    tz_offset = current_tz_offset_seconds()
    cache_path = cache_file_path(_CODEX_EVENT_CACHE_PROVIDER, expanded_dir, root=cache_root)
    if cache_path is None:
        return [_read_codex_file(fp) for fp in file_list]

    out: list[tuple[str, list[tuple[datetime, int, str, int]]]] = []
    with with_cache_lock(cache_path):
        cache = load_cache(cache_path)
        if _codex_event_cache_invalid(cache, expanded_dir, parser_version, tz_offset):
            cache = _empty_codex_event_cache(expanded_dir, parser_version, tz_offset)

        raw_files = cache.get("files")
        cached_files: dict[str, Any] = raw_files if isinstance(raw_files, dict) else {}
        new_files = dict(cached_files)

        for fp_real in file_list:
            fp_print = file_fingerprint(fp_real)
            if fp_print is None:
                continue
            cached = _decode_codex_cache_entry(new_files.get(fp_real), fp_print)
            if cached is not None:
                out.append(cached)
                continue

            session_id, events = _read_codex_file(fp_real)
            new_files[fp_real] = {
                "fingerprint": fp_print,
                "parsedAt": utc_now_iso(),
                "sessionId": session_id,
                "events": _encode_codex_events(events),
            }
            out.append((session_id, events))

        for fp_real in list(new_files):
            if not os.path.exists(fp_real):
                del new_files[fp_real]

        cache["files"] = new_files
        cache["updatedAt"] = utc_now_iso()
        save_cache_atomic(cache_path, cache)
    return out


def parse_codex_files(files: list[str], *, data_dir: str | None = None,
                      cache_root: Path | None = None
                      ) -> dict[str, dict[str, dict[str, int]]]:
    out: dict[str, dict[str, dict[str, int]]] = {}
    by_session: dict[str, list[tuple[datetime, int, int, str, int]]] = {}
    for file_index, (session_id, events) in enumerate(
            _read_codex_files(files, data_dir=data_dir, cache_root=cache_root)):
        bag = by_session.setdefault(session_id, [])
        for dt, seq, model, total in events:
            bag.append((dt, file_index, seq, model, total))

    for events in by_session.values():
        highwater_total = 0
        for dt, _file_index, _seq, model, total in sorted(events):
            if total <= highwater_total:
                continue
            delta = total - highwater_total
            highwater_total = total
            b = bucket_id(dt)
            _bump(out.setdefault(b, {}), model, raw=delta, billable=delta)
    return out


def parse_codex_file(fp: str) -> dict[str, dict[str, dict[str, int]]]:
    return parse_codex_files([fp])


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
    del start_date
    expanded = os.path.expanduser(data_dir)
    files: list[str] = []
    for pat in (
        os.path.join(expanded, "sessions", "**", "*.jsonl"),
        os.path.join(expanded, "archived_sessions", "*.jsonl"),
    ):
        files.extend(glob.glob(pat, recursive=True))
    # Do not period-filter here: pre-period snapshots can be required to seed
    # the session highwater. scan_codex caches per-file events to avoid reparsing
    # unchanged history on every refresh.
    return sorted(f for f in files if mtime_within(f, 0))


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
    mode = normalize_token_mode(mode)
    today = datetime.now().astimezone().date()
    start_d, _ = period_window(period, today=today)
    files = list_codex_files(data_dir, start_d)
    chart_meta, unit = period_chart_buckets(period, today=today)

    bucket_set = {b["id"] for b in chart_meta}
    by_bucket: dict[str, dict[str, int]] = {}
    model_totals: dict[str, int] = {}
    daily = parse_codex_files(files, data_dir=data_dir, cache_root=cache_root)
    for daily_id, models in daily.items():
        try:
            d = date.fromisoformat(daily_id)
        except (ValueError, TypeError):
            continue
        target_id = bucket_id_for_date(d, unit)
        if target_id not in bucket_set:
            continue
        bag = by_bucket.setdefault(target_id, {})
        for m, vals in models.items():
            if not (isinstance(m, str) and isinstance(vals, dict)):
                continue
            v = vals.get(mode)
            if not (isinstance(v, int) and not isinstance(v, bool) and v > 0):
                continue
            bag[m] = bag.get(m, 0) + v
            model_totals[m] = model_totals.get(m, 0) + v
    return by_bucket, model_totals, chart_meta, unit
