"""Dynamic fixture generator.

避免硬编码日期导致测试/CI 时间炸弹。生成的 jsonl/json 用 today/yesterday 时间戳，
保证 7d 窗口能覆盖。

CLI 用法（CI smoke 用）：
    python3 tests/_fixture_gen.py <target_root>
    # 生成 <target_root>/{claude,gemini,codex}/

测试用法：
    from tests._fixture_gen import generate
    generate(Path("/tmp/scratch"), today=date.today())
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def generate(target_root: Path, today: date | None = None) -> dict[str, Path]:
    """生成三家 fixture 到 target_root 下，返回 {provider: path} 映射。"""
    today = today or date.today()
    yesterday = today - timedelta(days=1)
    today_dt = datetime.combine(today, time(10, 0), tzinfo=timezone.utc)
    yest_dt = datetime.combine(yesterday, time(9, 0), tzinfo=timezone.utc)

    target_root.mkdir(parents=True, exist_ok=True)

    # ── Claude ────────────────────────────────────────────────────────────
    claude_dir = target_root / "claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    claude_file = claude_dir / "session-001.jsonl"
    lines = [
        {"type": "user", "message": {"role": "user", "content": "hi"},
         "timestamp": _iso(today_dt)},
        {"type": "assistant",
         "message": {"role": "assistant", "model": "claude-opus-4-7",
                     "content": "hello",
                     "usage": {"input_tokens": 12, "output_tokens": 34,
                               "cache_creation_input_tokens": 5,
                               "cache_read_input_tokens": 7}},
         "timestamp": _iso(today_dt + timedelta(seconds=5))},
        {"type": "assistant",
         "message": {"role": "assistant", "model": "claude-sonnet-4-6",
                     "content": "second",
                     "usage": {"input_tokens": 100, "output_tokens": 200}},
         "timestamp": _iso(today_dt + timedelta(hours=1))},
        {"type": "assistant",
         "message": {"role": "assistant", "model": "claude-opus-4-7",
                     "content": "yesterday",
                     "usage": {"input_tokens": 10, "output_tokens": 20}},
         "timestamp": _iso(yest_dt)},
        {"type": "assistant",
         "message": {"role": "assistant", "model": "no-tokens",
                     "usage": {"input_tokens": 0, "output_tokens": 0}},
         "timestamp": _iso(today_dt + timedelta(hours=2))},
    ]
    with open(claude_file, "w", encoding="utf-8") as fh:
        for ln in lines:
            fh.write(json.dumps(ln, ensure_ascii=False) + "\n")
        fh.write("this is not valid json and must be skipped\n")

    # ── Gemini ────────────────────────────────────────────────────────────
    gemini_dir = target_root / "gemini"
    gemini_dir.mkdir(parents=True, exist_ok=True)
    gemini_file = gemini_dir / "session-001.json"
    gemini_doc = {
        "sessionId": "test-001",
        "messages": [
            {"role": "user", "content": "hi", "timestamp": _iso(today_dt)},
            {"role": "assistant", "model": "gemini-2.5-pro", "content": "hello",
             "tokens": {"total": 150}, "timestamp": _iso(today_dt + timedelta(seconds=1))},
            {"role": "assistant", "model": "gemini-2.5-flash", "content": "second",
             "tokens": {"input": 50, "output": 80, "cached": 0,
                        "thoughts": 10, "tool": 5},
             "timestamp": _iso(today_dt + timedelta(hours=1))},
            {"role": "assistant", "model": "no-tokens",
             "tokens": {"total": 0},
             "timestamp": _iso(today_dt + timedelta(hours=2))},
        ],
    }
    with open(gemini_file, "w", encoding="utf-8") as fh:
        json.dump(gemini_doc, fh, ensure_ascii=False)

    # ── Codex ─────────────────────────────────────────────────────────────
    codex_dir = (target_root / "codex" / "sessions"
                 / today.strftime("%Y") / today.strftime("%m") / today.strftime("%d"))
    codex_dir.mkdir(parents=True, exist_ok=True)
    codex_filename = f"rollout-{today.strftime('%Y-%m-%d')}T10-00-00-test123.jsonl"
    codex_file = codex_dir / codex_filename
    codex_lines = [
        {"type": "turn_context",
         "payload": {"model": "gpt-5.5", "timestamp": _iso(today_dt)}},
        {"type": "token_count",
         "payload": {"type": "token_count",
                     "timestamp": _iso(today_dt + timedelta(seconds=5)),
                     "info": {"total_token_usage": {"total_tokens": 100}}}},
        {"type": "token_count",
         "payload": {"type": "token_count",
                     "timestamp": _iso(today_dt + timedelta(seconds=60)),
                     "info": {"total_token_usage": {"total_tokens": 300}}}},
        {"type": "turn_context",
         "payload": {"model": "gpt-5.5-codex",
                     "timestamp": _iso(today_dt + timedelta(hours=1))}},
        {"type": "token_count",
         "payload": {"type": "token_count",
                     "timestamp": _iso(today_dt + timedelta(hours=1, seconds=30)),
                     "info": {"total_token_usage": {"total_tokens": 500}}}},
    ]
    with open(codex_file, "w", encoding="utf-8") as fh:
        for ln in codex_lines:
            fh.write(json.dumps(ln, ensure_ascii=False) + "\n")

    # 刷新 mtime 到 today（确保 mtime 预过滤通过）
    now_ts = datetime.now().timestamp()
    for p in (claude_file, gemini_file, codex_file):
        os.utime(p, (now_ts, now_ts))

    return {
        "claude": claude_dir,
        "gemini": gemini_dir,
        "codex":  target_root / "codex",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", type=Path, help="output root for fixtures")
    args = ap.parse_args()
    paths = generate(args.target)
    for prov, p in paths.items():
        print(f"{prov}\t{p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
