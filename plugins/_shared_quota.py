"""Claude 官方账号额度（5h / 周）获取、缓存与 item 构建。

只在本机能读到 Claude Code 官方 OAuth 凭据时生效；纯 API key /
中转（CPA 等）环境读不到凭据，额度区与账号邮箱整体自动隐藏。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from _shared_cache import cache_dir
from _shared_core import parse_iso, tr

OAUTH_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA_HEADER = "oauth-2025-04-20"
FETCH_TIMEOUT_SECONDS = 3
QUOTA_CACHE_TTL_SECONDS = 120          # TTL 内直接用缓存，不打 API
QUOTA_STALE_MAX_SECONDS = 30 * 60      # 请求失败时旧缓存的兜底上限
KEYCHAIN_SERVICE = "Claude Code-credentials"

_QUOTA_WINDOWS = (("five_hour", "quota_5h"), ("seven_day", "quota_week"))


def read_account_email(claude_json_path: str = "~/.claude.json") -> str | None:
    try:
        with open(os.path.expanduser(claude_json_path), encoding="utf-8") as fh:
            data = json.load(fh)
        email = (data.get("oauthAccount") or {}).get("emailAddress")
        return email if isinstance(email, str) and "@" in email else None
    except (OSError, ValueError):
        return None


def read_oauth_token(creds_path: str = "~/.claude/.credentials.json") -> str | None:
    raw: str | None = None
    try:
        with open(os.path.expanduser(creds_path), encoding="utf-8") as fh:
            raw = fh.read()
    except OSError:
        try:
            raw = subprocess.run(
                ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                capture_output=True, text=True, timeout=5, check=True,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return None
    try:
        token = (json.loads(raw).get("claudeAiOauth") or {}).get("accessToken")
        return token if isinstance(token, str) and token else None
    except (ValueError, AttributeError):
        return None


def fetch_usage(token: str, *, timeout: int = FETCH_TIMEOUT_SECONDS) -> dict[str, Any]:
    """请求官方额度接口。401/403 时抛 PermissionError，其它失败抛原异常。"""
    req = urllib.request.Request(OAUTH_USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": OAUTH_BETA_HEADER,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise PermissionError(f"oauth usage api returned {exc.code}") from exc
        raise


def _extract_windows(payload: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    out: dict[str, dict[str, Any]] = {}
    for key, _label in _QUOTA_WINDOWS:
        win = payload.get(key)
        if not isinstance(win, dict) or win.get("utilization") is None:
            continue
        try:
            utilization = float(win["utilization"])
        except (TypeError, ValueError):
            continue
        resets_at = None
        parsed = parse_iso(win.get("resets_at"))
        if parsed is not None:
            resets_at = (parsed.astimezone(timezone.utc).replace(microsecond=0)
                         .isoformat().replace("+00:00", "Z"))
        out[key] = {"utilization": utilization, "resets_at": resets_at}
    return out or None


def _quota_cache_path(root: Path | None = None) -> Path | None:
    base = cache_dir(root=root)
    return base / "claude-quota.cache.json" if base is not None else None


def _read_cache(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            cached = json.load(fh)
        return cached if isinstance(cached, dict) and cached.get("windows") else None
    except (OSError, ValueError):
        return None


def _write_cache(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        print(f"[quota] cache write failed ({exc})", file=sys.stderr)


def _cache_age(cached: dict[str, Any], now: datetime) -> float | None:
    fetched_at = parse_iso(cached.get("fetchedAt"))
    if fetched_at is None:
        return None
    return (now - fetched_at).total_seconds()


def get_quota(*, now: datetime | None = None,
              token_reader: Callable[[], str | None] = read_oauth_token,
              fetcher: Callable[[str], dict[str, Any]] = fetch_usage,
              cache_root: Path | None = None) -> dict[str, dict[str, Any]] | None:
    """返回 {"five_hour": {...}, "seven_day": {...}} 或 None（隐藏额度区）。"""
    now = now or datetime.now(timezone.utc)
    cache_path = _quota_cache_path(cache_root)
    cached = _read_cache(cache_path)
    if cached is not None:
        age = _cache_age(cached, now)
        if age is not None and 0 <= age <= QUOTA_CACHE_TTL_SECONDS:
            return cached["windows"]

    token = token_reader()
    if not token:
        return None

    try:
        payload = fetcher(token)
    except PermissionError as exc:
        print(f"[quota] {exc}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"[quota] fetch failed: {exc}", file=sys.stderr)
        if cached is not None:
            age = _cache_age(cached, now)
            if age is not None and 0 <= age <= QUOTA_STALE_MAX_SECONDS:
                return cached["windows"]
        return None

    windows = _extract_windows(payload)
    if windows is None:
        print("[quota] usage api payload missing quota windows", file=sys.stderr)
        return None
    _write_cache(cache_path, {
        "fetchedAt": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "windows": windows,
    })
    return windows


def build_quota_items(windows: dict[str, dict[str, Any]], language: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key, label_key in _QUOTA_WINDOWS:
        win = windows.get(key)
        if not win:
            continue
        utilization = max(float(win.get("utilization") or 0.0), 0.0)
        status = "critical" if utilization >= 85 else "warning" if utilization >= 60 else "normal"
        color = "red" if utilization >= 85 else "orange" if utilization >= 60 else "blue"
        items.append({
            "id": f"claude-quota-{key}",
            "name": tr(language, label_key),
            "used": round(min(utilization, 100.0), 1),
            "limit": 100.0,
            "displayStyle": "percent",
            "resetAt": win.get("resets_at"),
            "status": status, "color": color,
        })
    return items
