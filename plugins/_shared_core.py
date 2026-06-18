"""Core constants and small helpers shared by TokenUsed plugins."""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

SCHEMA_VERSION = 1
CACHE_VERSION = 2

PARSER_VERSIONS = {
    "claude": "v3",  # v3: 按 message.id 去重重复 assistant usage 行
    "gemini": "v2",
    "codex": "v3",  # v3: total_token_usage 用 session 高水位增量
}

TOKEN_MODES = ("billable", "raw")
DEFAULT_TOKEN_MODE = "billable"

PERIODS = ("today", "7d", "30d", "90d", "all")
DEFAULT_PERIOD = "30d"

CACHE_PRUNE_DAYS = 400  # 覆盖 12 个月 all 视图，并给时区/月底留余量

TRANSLATIONS: dict[str, dict[str, str]] = {
    "no_data": {"en": "No stats data available", "zh-Hans": "暂无可用统计数据"},
    "no_data_today": {"en": "No usage today", "zh-Hans": "今日暂无用量"},
    "scan_failed": {"en": "Failed to scan sessions", "zh-Hans": "扫描会话失败"},
    "period_today": {"en": "Today", "zh-Hans": "今日"},
    "period_7d": {"en": "7d", "zh-Hans": "7 天"},
    "period_30d": {"en": "30d", "zh-Hans": "30 天"},
    "period_90d": {"en": "90d", "zh-Hans": "90 天"},
    "period_all": {"en": "All", "zh-Hans": "全部"},
    "today_total": {"en": "Today", "zh-Hans": "今日合计"},
    "this_week_total": {"en": "This week", "zh-Hans": "本周合计"},
    "this_month_total": {"en": "This month", "zh-Hans": "本月合计"},
    "total_tokens_for_period": {"en": "{period} total", "zh-Hans": "{period} 总用量"},
    "token_mode": {"en": "token mode", "zh-Hans": "token 口径"},
    "mode_billable": {"en": "billable", "zh-Hans": "计费"},
    "mode_raw": {"en": "raw", "zh-Hans": "原始"},
    "other_model": {"en": "Other {count} model", "zh-Hans": "其他 {count} 个模型"},
    "other_models": {"en": "Other {count} models", "zh-Hans": "其他 {count} 个模型"},
    "quota_5h": {"en": "Claude 5h limit", "zh-Hans": "Claude 5h 额度"},
    "quota_week": {"en": "Claude weekly", "zh-Hans": "Claude 周额度"},
}


def normalize_token_mode(value: str | None) -> str:
    v = (value or "").strip().lower()
    return v if v in TOKEN_MODES else DEFAULT_TOKEN_MODE


def normalize_period(value: str | None) -> str:
    v = (value or "").strip().lower()
    return v if v in PERIODS else DEFAULT_PERIOD


def parse_params(argv: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    i = 0
    while i < len(argv):
        if argv[i] == "--usageboard-param" and i + 1 < len(argv):
            kv = argv[i + 1]
            if "=" in kv:
                k, v = kv.split("=", 1)
                out[k] = v
            i += 2
        else:
            i += 1
    return out


def lang(p: dict[str, str]) -> str:
    raw = (p.get("USAGEBOARD_LANGUAGE") or "zh-Hans").lower()
    if raw.startswith("en"):
        return "en"
    return "zh-Hans"


def tr(language: str, key: str) -> str:
    bag = TRANSLATIONS.get(key, {})
    return bag.get(language) or bag.get("zh-Hans") or key


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone()
    except (ValueError, TypeError):
        return None


def period_window(period: str, *, today: date | None = None) -> tuple[date, date]:
    """返回该 period 在 daily 粒度上的 (start_date, end_date)，给 mtime cutoff / 文件枚举用。"""
    base = today or datetime.now().astimezone().date()
    if period == "today":
        return base, base
    if period == "7d":
        return base - timedelta(days=6), base
    if period == "30d":
        return base - timedelta(days=29), base
    if period == "90d":
        return base - timedelta(days=89), base
    if period == "all":
        total = base.year * 12 + base.month - 1 - 11
        y, m = total // 12, total % 12 + 1
        return date(y, m, 1), base
    return base - timedelta(days=6), base


def period_chart_buckets(period: str, *, today: date | None = None
                         ) -> tuple[list[dict[str, str]], str]:
    """返回 (buckets_meta, bucket_unit)。bucket_unit ∈ {day, week, month}。"""
    base = today or datetime.now().astimezone().date()
    if period == "today":
        return ([{"id": base.isoformat(), "label": base.strftime("%m-%d"),
                  "start": base.isoformat(), "end": base.isoformat()}], "day")
    if period in ("7d", "30d"):
        days = 7 if period == "7d" else 30
        start = base - timedelta(days=days - 1)
        out = []
        for i in range(days):
            d = start + timedelta(days=i)
            out.append({"id": d.isoformat(), "label": d.strftime("%m-%d"),
                        "start": d.isoformat(), "end": d.isoformat()})
        return out, "day"
    if period == "90d":
        weekday = base.weekday()
        this_monday = base - timedelta(days=weekday)
        out = []
        for i in range(12, -1, -1):
            ws = this_monday - timedelta(weeks=i)
            we = ws + timedelta(days=6)
            y, w, _ = ws.isocalendar()
            out.append({"id": f"{y}-W{w:02d}", "label": ws.strftime("%m-%d"),
                        "start": ws.isoformat(), "end": we.isoformat()})
        return out, "week"
    if period == "all":
        out = []
        for i in range(11, -1, -1):
            total = base.year * 12 + base.month - 1 - i
            y, m = total // 12, total % 12 + 1
            ms = date(y, m, 1)
            me = (date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)) - timedelta(days=1)
            out.append({"id": f"{y:04d}-{m:02d}", "label": f"{m}月",
                        "start": ms.isoformat(), "end": me.isoformat()})
        return out, "month"
    return period_chart_buckets("7d", today=base)


def stat_range(period: str, *, now: datetime | None = None
                ) -> tuple[datetime, datetime, list[datetime]]:
    """兼容性 stub: 老调用点给 datetime 接口；返回 daily datetime 列表。"""
    base = (now or datetime.now()).astimezone()
    start_d, end_d = period_window(period, today=base.date())
    days_count = (end_d - start_d).days + 1
    start = datetime.combine(start_d, time.min, tzinfo=base.tzinfo)
    end = datetime.combine(end_d, time.max, tzinfo=base.tzinfo)
    buckets = [start + timedelta(days=i) for i in range(days_count)]
    return start, end, buckets


def bucket_id(dt: datetime | date) -> str:
    return dt.strftime("%Y-%m-%d")


def bucket_label(dt: datetime | date) -> str:
    return dt.strftime("%m-%d")


def bucket_id_for_date(d: date, unit: str) -> str:
    if unit == "week":
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}"
    if unit == "month":
        return f"{d.year:04d}-{d.month:02d}"
    return d.isoformat()


def current_tz_offset_seconds() -> int:
    off = datetime.now().astimezone().utcoffset()
    return int(off.total_seconds()) if off is not None else 0


def fmt_tokens(n: int | float, language: str = "en") -> str:
    n = int(n)
    if n < 0:
        n = 0
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def mtime_cutoff(first_bucket: datetime, *, slack_days: int = 2) -> float:
    return first_bucket.timestamp() - slack_days * 86400


def mtime_within(path: str, cutoff_ts: float) -> bool:
    try:
        return os.path.getmtime(path) >= cutoff_ts
    except OSError:
        return True
