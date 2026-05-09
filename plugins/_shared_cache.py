"""File-level cache and aggregation helpers for TokenUsed plugins."""
from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

from _shared_core import (
    CACHE_PRUNE_DAYS,
    CACHE_VERSION,
    DEFAULT_TOKEN_MODE,
    SCHEMA_VERSION,
    bucket_id_for_date,
    current_tz_offset_seconds,
    normalize_token_mode,
    utc_now_iso,
)


def cache_dir(*, root: Path | None = None) -> Path | None:
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
    """跨进程独占锁。失败时降级（不锁），plugin 仍能输出 JSON。"""
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
    bucket_unit: str = "day",
    cache_root: Path | None = None,
) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    mode = normalize_token_mode(mode)
    expanded_dir = os.path.realpath(os.path.expanduser(data_dir))
    tz_offset = current_tz_offset_seconds()
    cache_path = cache_file_path(provider, expanded_dir, root=cache_root)

    file_list = list(files)
    new_files: dict[str, dict[str, Any]] = {}

    if cache_path is None:
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

            raw_files = cache.get("files")
            cached_files: dict[str, dict[str, Any]] = {}
            if isinstance(raw_files, dict):
                for k, v in raw_files.items():
                    if not (isinstance(k, str)
                            and isinstance(v, dict)
                            and isinstance(v.get("fingerprint"), dict)
                            and isinstance(v.get("byBucket"), dict)):
                        continue
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
                    new_files[fp_real] = entry
                    continue
                try:
                    by_bucket_one = parse_file(fp_real) or {}
                except Exception as exc:
                    print(f"[{provider}] parse_file failed for {fp_real}: {exc}",
                          file=sys.stderr)
                    new_files.pop(fp_real, None)
                    continue
                new_files[fp_real] = {
                    "fingerprint": fp_print,
                    "parsedAt": utc_now_iso(),
                    "byBucket": by_bucket_one,
                }

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

    by_bucket: dict[str, dict[str, int]] = {}
    model_totals: dict[str, int] = {}
    for entry in new_files.values():
        by = entry.get("byBucket") or {}
        for daily_id, models in by.items():
            if not (isinstance(daily_id, str) and isinstance(models, dict)):
                continue
            try:
                d = date.fromisoformat(daily_id)
            except (ValueError, TypeError):
                continue
            target_id = bucket_id_for_date(d, bucket_unit)
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
    return by_bucket, model_totals
