"""TokenUsed plugin shared library.

被 4 个 plugin 通过 sys.path 注入后 `from _shared import ...` 使用。
本模块严禁向 stdout 输出任何东西（plugin 的 stdout 留给最终 JSON）。
错误一律写 stderr，UsageBoard 会展示。
"""
from __future__ import annotations

import errno
import fcntl
import glob
import hashlib
import json
import os
import re
import sys
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

SCHEMA_VERSION = 1
CACHE_VERSION = 1

PARSER_VERSIONS = {
    "claude": "v2",  # v2: byBucket value 改为 {"raw": N, "billable": N}
    "gemini": "v2",
    "codex": "v2",
}

TOKEN_MODES = ("billable", "raw")
DEFAULT_TOKEN_MODE = "billable"


def normalize_token_mode(value: str | None) -> str:
    v = (value or "").strip().lower()
    return v if v in TOKEN_MODES else DEFAULT_TOKEN_MODE

CACHE_PRUNE_DAYS = 45  # cache 中超过该天数无活动的文件 entry 会被清理

TRANSLATIONS: dict[str, dict[str, str]] = {
    "no_data": {"en": "No stats data available", "zh-Hans": "暂无可用统计数据"},
    "no_data_today": {"en": "No usage today", "zh-Hans": "今日暂无用量"},
    "scan_failed": {"en": "Failed to scan sessions", "zh-Hans": "扫描会话失败"},
    "period_7d": {"en": "7d", "zh-Hans": "7 天"},
    "period_30d": {"en": "30d", "zh-Hans": "30 天"},
    "today_total": {"en": "Today total", "zh-Hans": "今日合计"},
    "total_tokens_for_period": {"en": "{period} total", "zh-Hans": "{period} 总用量"},
    "mode_billable": {"en": "billable", "zh-Hans": "计费"},
    "mode_raw": {"en": "raw", "zh-Hans": "原始"},
}


# ─────────────────────────────── params / i18n ───────────────────────────────

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


# ───────────────────────────────── time utils ────────────────────────────────

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone()
    except (ValueError, TypeError):
        return None


def stat_range(period: str, *, now: datetime | None = None
                ) -> tuple[datetime, datetime, list[datetime]]:
    """返回 (start, end, buckets) — 本地时区的日桶序列。

    period: '7d' or '30d'。其他值按 7d 处理。
    """
    days = 30 if period == "30d" else 7
    base = (now or datetime.now()).astimezone()
    today = base.date()
    start_date = today - timedelta(days=days - 1)
    start = datetime.combine(start_date, time.min, tzinfo=base.tzinfo)
    end = datetime.combine(today, time.max, tzinfo=base.tzinfo)
    buckets = [start + timedelta(days=i) for i in range(days)]
    return start, end, buckets


def bucket_id(dt: datetime | date) -> str:
    return dt.strftime("%Y-%m-%d")


def bucket_label(dt: datetime | date) -> str:
    return dt.strftime("%m-%d")


def current_tz_offset_seconds() -> int:
    """返回当前本地时区相对 UTC 的偏移秒数，作为 cache 失效字段。"""
    off = datetime.now().astimezone().utcoffset()
    return int(off.total_seconds()) if off is not None else 0


# ─────────────────────────────── token format ────────────────────────────────

def fmt_tokens(n: int | float, language: str = "en") -> str:
    n = int(n)
    if n < 0:
        n = 0
    if language == "zh-Hans":
        if n >= 100_000_000:
            return f"{n / 100_000_000:.2f}亿"
        if n >= 10_000:
            return f"{n / 10_000:.2f}万"
        return str(n)
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


# ─────────────────────────────── mtime filter ────────────────────────────────

def mtime_cutoff(first_bucket: datetime, *, slack_days: int = 2) -> float:
    return first_bucket.timestamp() - slack_days * 86400


def mtime_within(path: str, cutoff_ts: float) -> bool:
    try:
        return os.path.getmtime(path) >= cutoff_ts
    except OSError:
        return True


# ──────────────────────────────── cache layer ────────────────────────────────

def cache_dir(*, root: Path | None = None) -> Path | None:
    """Return cache directory, creating it if missing.

    Returns None on failure so callers degrade to no-cache full parse.
    """
    base = root if root is not None else Path(os.path.expanduser("~/Library/Caches/UsageBoard"))
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"[_shared] cache dir unavailable ({exc}); proceeding without cache", file=sys.stderr)
        return None
    return base


def cache_file_path(provider: str, data_dir: str, *, root: Path | None = None) -> Path | None:
    base = cache_dir(root=root)
    if base is None:
        return None
    h = hashlib.sha256(os.path.realpath(os.path.expanduser(data_dir)).encode("utf-8")).hexdigest()[:12]
    return base / f"{provider}-{h}.cache.json"


def file_fingerprint(path: str) -> dict[str, int] | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return {"size": int(st.st_size), "mtimeNs": int(st.st_mtime_ns)}


@contextmanager
def with_cache_lock(cache_path: Path):
    """跨进程独占锁。失败时降级（不锁），plugin 仍能输出 JSON。

    `try` 仅覆盖 open + flock；with-body 自身的异常会冒泡，不会误走降级分支。
    """
    lock_path = cache_path.with_suffix(cache_path.suffix + ".lock")
    fh = None
    locked = False
    try:
        fh = open(lock_path, "a+")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        locked = True
    except OSError as exc:
        print(f"[_shared] cache lock failed ({exc}); proceeding without lock", file=sys.stderr)
        if fh is not None:
            try:
                fh.close()
            except OSError:
                pass
            fh = None
    try:
        yield fh
    finally:
        if locked and fh is not None:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        if fh is not None:
            try:
                fh.close()
            except OSError:
                pass


def load_cache(path: Path) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def save_cache_atomic(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError as exc:
        print(f"[_shared] cache write failed ({exc})", file=sys.stderr)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def merge_bucket_maps(dst: dict[str, dict[str, int]],
                      src: dict[str, dict[str, int]]) -> None:
    for b, models in src.items():
        bag = dst.setdefault(b, {})
        for m, t in models.items():
            bag[m] = bag.get(m, 0) + int(t)


def _empty_cache(provider: str, data_dir: str, parser_version: str,
                 tz_offset: int) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "cacheVersion": CACHE_VERSION,
        "provider": provider,
        "dataDir": data_dir,
        "parserVersion": parser_version,
        "tzOffsetSeconds": tz_offset,
        "updatedAt": utc_now_iso(),
        "files": {},
    }


def _cache_invalid(cache: dict[str, Any], provider: str, data_dir: str,
                   parser_version: str, tz_offset: int) -> bool:
    if cache.get("cacheVersion") != CACHE_VERSION:
        return True
    if cache.get("provider") != provider:
        return True
    if cache.get("parserVersion") != parser_version:
        return True
    if cache.get("dataDir") != data_dir:
        return True
    raw_tz = cache.get("tzOffsetSeconds")
    if not isinstance(raw_tz, (int, float)) or int(raw_tz) != tz_offset:
        return True
    return False


def aggregate_with_cache(
    *,
    provider: str,
    data_dir: str,
    files: Iterable[str],
    parse_file: Callable[[str], dict[str, dict[str, dict[str, int]]]],
    parser_version: str,
    bucket_set: set[str],
    mode: str = DEFAULT_TOKEN_MODE,
    cache_root: Path | None = None,
) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    """File-level cache 编排（v2 schema：双值 raw/billable 并存）。

    parse_file(path) 必须是纯函数，返回 {bucket_id: {model: {"raw": N, "billable": N}}}，
    覆盖该文件**所有**桶（不要预过滤窗口——cache 服务于 7d/30d 双窗口）。
    切换 `mode` 时不会触发 reparse，aggregate 阶段按 mode 投影到 int。

    返回 (by_bucket, model_totals) 已按 bucket_set 过滤、按 mode 投影。
    """
    mode = normalize_token_mode(mode)
    expanded_dir = os.path.realpath(os.path.expanduser(data_dir))
    tz_offset = current_tz_offset_seconds()
    cache_path = cache_file_path(provider, expanded_dir, root=cache_root)

    file_list = list(files)
    new_files: dict[str, dict[str, Any]] = {}

    if cache_path is None:
        # cache 不可用（目录创建失败等）：全量 parse，不写盘
        for fp in file_list:
            fp_real = os.path.realpath(fp)
            fp_print = file_fingerprint(fp_real)
            if fp_print is None:
                continue
            try:
                by_bucket_one = parse_file(fp_real) or {}
            except Exception as exc:
                print(f"[{provider}] parse_file failed for {fp_real}: {exc}", file=sys.stderr)
                continue
            new_files[fp_real] = {"fingerprint": fp_print, "parsedAt": utc_now_iso(),
                                   "byBucket": by_bucket_one}
    else:
        with with_cache_lock(cache_path):
            cache = load_cache(cache_path)
            if _cache_invalid(cache, provider, expanded_dir, parser_version, tz_offset):
                cache = _empty_cache(provider, expanded_dir, parser_version, tz_offset)

            # 严格校验 files 字段类型；不合规则整份当首次（仅丢 files，保留头部元数据）
            # v2 schema 要求 byBucket 的 model 值是 dict（{raw, billable}）而非 int
            raw_files = cache.get("files")
            cached_files: dict[str, dict[str, Any]] = {}
            if isinstance(raw_files, dict):
                for k, v in raw_files.items():
                    if not (isinstance(k, str)
                            and isinstance(v, dict)
                            and isinstance(v.get("fingerprint"), dict)
                            and isinstance(v.get("byBucket"), dict)):
                        continue
                    # 检查 byBucket → model → {raw, billable} 结构
                    # bucket key 必须 str（prune 会做 b >= cutoff_str 比较）
                    # model key 必须 str（流入 JSON 输出）
                    # raw/billable 必须 int（不接受 bool / float 含 NaN/Inf 风险）
                    ok = True
                    for _b, models in v["byBucket"].items():
                        if not (isinstance(_b, str) and isinstance(models, dict)):
                            ok = False; break
                        for _m, vals in models.items():
                            if not (isinstance(_m, str) and isinstance(vals, dict)):
                                ok = False; break
                            r = vals.get("raw"); b_ = vals.get("billable")
                            if not (isinstance(r, int) and not isinstance(r, bool)
                                    and isinstance(b_, int) and not isinstance(b_, bool)
                                    and r >= 0 and b_ >= 0):
                                ok = False; break
                        if not ok: break
                    if ok:
                        cached_files[k] = v
            # 起始 = 旧 cache（保留 file_list 之外但仍在窗口内的 entry，避免 7d/30d 互踢）
            new_files = dict(cached_files)
            prune_cutoff = (datetime.now().astimezone()
                            - timedelta(days=CACHE_PRUNE_DAYS)).date().isoformat()

            for fp in file_list:
                fp_real = os.path.realpath(fp)
                fp_print = file_fingerprint(fp_real)
                if fp_print is None:
                    continue
                entry = cached_files.get(fp_real)
                if (entry is not None
                        and entry.get("fingerprint") == fp_print):
                    # 命中：保留（已通过严格类型校验）
                    new_files[fp_real] = entry
                    continue
                try:
                    by_bucket_one = parse_file(fp_real) or {}
                except Exception as exc:
                    print(f"[{provider}] parse_file failed for {fp_real}: {exc}",
                          file=sys.stderr)
                    # parse 失败：剔除可能残留的旧 stale entry（避免本次输出含过时数据）
                    new_files.pop(fp_real, None)
                    continue
                new_files[fp_real] = {
                    "fingerprint": fp_print,
                    "parsedAt": utc_now_iso(),
                    "byBucket": by_bucket_one,
                }

            # Prune:
            # 1) 文件不存在 → 删
            # 2) per-bucket 删除 < prune_cutoff 的老桶
            # 3) byBucket 全空 → 保留 entry 但置空（fingerprint 仍能跳过 reparse）
            for fp_real, entry in list(new_files.items()):
                if not os.path.exists(fp_real):
                    del new_files[fp_real]
                    continue
                by = entry.get("byBucket") or {}
                fresh = {b: m for b, m in by.items() if b >= prune_cutoff}
                if len(fresh) != len(by):
                    new_files[fp_real] = {**entry, "byBucket": fresh}

            cache["files"] = new_files
            cache["updatedAt"] = utc_now_iso()
            save_cache_atomic(cache_path, cache)

    # Aggregate within window，按 mode 投影 {raw, billable} → int
    by_bucket: dict[str, dict[str, int]] = {}
    model_totals: dict[str, int] = {}
    for entry in new_files.values():
        by = entry.get("byBucket") or {}
        for b, models in by.items():
            if not (isinstance(b, str) and b in bucket_set and isinstance(models, dict)):
                continue
            bag = by_bucket.setdefault(b, {})
            for m, vals in models.items():
                if not (isinstance(m, str) and isinstance(vals, dict)):
                    continue
                v = vals.get(mode)
                if not (isinstance(v, int) and not isinstance(v, bool) and v > 0):
                    continue
                bag[m] = bag.get(m, 0) + v
                model_totals[m] = model_totals.get(m, 0) + v
    return by_bucket, model_totals


# ─────────────────────────── provider file parsers ───────────────────────────

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
    """Add (raw, billable) into bag[model]. bag value is {"raw": int, "billable": int}."""
    cur = bag.get(model)
    if cur is None:
        bag[model] = {"raw": int(raw), "billable": int(billable)}
    else:
        cur["raw"] = int(cur.get("raw", 0)) + int(raw)
        cur["billable"] = int(cur.get("billable", 0)) + int(billable)


def parse_claude_file(fp: str) -> dict[str, dict[str, dict[str, int]]]:
    """Parse a Claude Code session JSONL.

    返回 {bucket_id: {model: {"raw": N, "billable": N}}}：
    - raw      = input + output + cache_creation + cache_read（含 cache 命中）
    - billable = input + output + cache_creation（与 Claude Code /cost 口径一致）

    字符串预筛只检查 `"usage"`，不依赖 JSON 字段顺序。
    """
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
    """Gemini 没有 cache_read 概念，raw 与 billable 数值相等。"""
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
    """Codex 没有 cache_read 概念，raw 与 billable 数值相等（取 total_tokens delta）。"""
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


# ───────────────────────────── file enumeration ──────────────────────────────

_CODEX_FILENAME_DATE = re.compile(r"rollout-(\d{4}-\d{2}-\d{2})T")


def list_claude_files(data_dir: str, cutoff_ts: float) -> list[str]:
    expanded = os.path.expanduser(data_dir)
    files = glob.glob(os.path.join(expanded, "**", "*.jsonl"), recursive=True)
    return [f for f in files if mtime_within(f, cutoff_ts)]


def list_gemini_files(data_dir: str, cutoff_ts: float) -> list[str]:
    expanded = os.path.expanduser(data_dir)
    files = glob.glob(os.path.join(expanded, "**", "session-*.json"), recursive=True)
    return [f for f in files if mtime_within(f, cutoff_ts)]


def list_codex_files(data_dir: str, start_date: date) -> list[str]:
    """Codex 用文件名日期过滤 + mtime fallback。"""
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


# ─────────────────────────── high-level provider scan ────────────────────────

def scan_claude(data_dir: str, buckets: list[datetime], *,
                mode: str = DEFAULT_TOKEN_MODE, cache_root: Path | None = None
                ) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    cutoff = mtime_cutoff(buckets[0])
    files = list_claude_files(data_dir, cutoff)
    return aggregate_with_cache(
        provider="claude",
        data_dir=data_dir,
        files=files,
        parse_file=parse_claude_file,
        parser_version=PARSER_VERSIONS["claude"],
        bucket_set={bucket_id(b) for b in buckets},
        mode=mode,
        cache_root=cache_root,
    )


def scan_gemini(data_dir: str, buckets: list[datetime], *,
                mode: str = DEFAULT_TOKEN_MODE, cache_root: Path | None = None
                ) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    cutoff = mtime_cutoff(buckets[0])
    files = list_gemini_files(data_dir, cutoff)
    return aggregate_with_cache(
        provider="gemini",
        data_dir=data_dir,
        files=files,
        parse_file=parse_gemini_file,
        parser_version=PARSER_VERSIONS["gemini"],
        bucket_set={bucket_id(b) for b in buckets},
        mode=mode,
        cache_root=cache_root,
    )


def scan_codex(data_dir: str, buckets: list[datetime], *,
               mode: str = DEFAULT_TOKEN_MODE, cache_root: Path | None = None
               ) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    files = list_codex_files(data_dir, buckets[0].date())
    return aggregate_with_cache(
        provider="codex",
        data_dir=data_dir,
        files=files,
        parse_file=parse_codex_file,
        parser_version=PARSER_VERSIONS["codex"],
        bucket_set={bucket_id(b) for b in buckets},
        mode=mode,
        cache_root=cache_root,
    )
