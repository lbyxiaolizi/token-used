"""
TokenUsed plugin tests — pure stdlib unittest, no pytest dependency.

Run:    python3 -m unittest tests.test_plugins -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGINS = REPO_ROOT / "plugins"

sys.path.insert(0, str(PLUGINS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _shared  # noqa: E402
from _fixture_gen import generate as gen_fixtures  # noqa: E402


def _today_buckets(days: int = 7) -> list[datetime]:
    today = datetime.now().astimezone().date()
    start = today - timedelta(days=days - 1)
    base = datetime.now().astimezone()
    return [datetime.combine(start + timedelta(days=i), time.min, tzinfo=base.tzinfo)
            for i in range(days)]


# ─────────────────────────── pure-function tests ────────────────────────────

class FmtTokensTests(unittest.TestCase):
    def test_en_units(self):
        self.assertEqual(_shared.fmt_tokens(0, "en"), "0")
        self.assertEqual(_shared.fmt_tokens(999, "en"), "999")
        self.assertEqual(_shared.fmt_tokens(1500, "en"), "1.5k")
        self.assertEqual(_shared.fmt_tokens(2_500_000, "en"), "2.50M")
        self.assertEqual(_shared.fmt_tokens(3_500_000_000, "en"), "3.50B")

    def test_zh_units(self):
        self.assertEqual(_shared.fmt_tokens(9999, "zh-Hans"), "9999")
        self.assertEqual(_shared.fmt_tokens(15_000, "zh-Hans"), "1.50万")
        self.assertEqual(_shared.fmt_tokens(150_000_000, "zh-Hans"), "1.50亿")

    def test_negative_clamped(self):
        self.assertEqual(_shared.fmt_tokens(-100, "en"), "0")


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="tokenused-parsers-"))
        self.paths = gen_fixtures(self.scratch)
        self.today = date.today()

    def tearDown(self):
        shutil.rmtree(self.scratch, ignore_errors=True)

    def test_claude(self):
        fp = next((self.paths["claude"]).glob("*.jsonl"))
        out = _shared.parse_claude_file(str(fp))
        today_id = self.today.isoformat()
        self.assertIn(today_id, out)
        bag = out[today_id]
        self.assertEqual(bag.get("claude-opus-4-7"), 12 + 34 + 5 + 7)
        self.assertEqual(bag.get("claude-sonnet-4-6"), 100 + 200)
        self.assertNotIn("no-tokens", bag)
        # 昨天那条
        yest = (self.today - timedelta(days=1)).isoformat()
        self.assertIn(yest, out)
        self.assertEqual(out[yest].get("claude-opus-4-7"), 30)

    def test_gemini(self):
        fp = next((self.paths["gemini"]).glob("*.json"))
        out = _shared.parse_gemini_file(str(fp))
        today_id = self.today.isoformat()
        self.assertIn(today_id, out)
        bag = out[today_id]
        self.assertEqual(bag.get("gemini-2.5-pro"), 150)
        self.assertEqual(bag.get("gemini-2.5-flash"), 50 + 80 + 0 + 10 + 5)
        self.assertNotIn("no-tokens", bag)

    def test_codex(self):
        fp = next((self.paths["codex"] / "sessions").rglob("*.jsonl"))
        out = _shared.parse_codex_file(str(fp))
        today_id = self.today.isoformat()
        self.assertIn(today_id, out)
        bag = out[today_id]
        # gpt-5.5 第一次 100 + 第二次 200 = 300; gpt-5.5-codex 第三次 200
        self.assertEqual(bag.get("gpt-5.5"), 300)
        self.assertEqual(bag.get("gpt-5.5-codex"), 200)


# ─────────────────────────── cache layer tests ──────────────────────────────

class CacheRoundtripTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tokenused-cache-")
        self.cache_root = Path(self.tmp)
        self.scratch = Path(tempfile.mkdtemp(prefix="tokenused-data-"))
        self.paths = gen_fixtures(self.scratch)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.scratch, ignore_errors=True)

    def _aggregate(self, parser_version: str, counter: dict[str, int]):
        buckets = _today_buckets(7)
        files = _shared.list_claude_files(str(self.paths["claude"]),
                                          _shared.mtime_cutoff(buckets[0]))
        def counting_parse(fp):
            counter["n"] += 1
            return _shared.parse_claude_file(fp)
        return _shared.aggregate_with_cache(
            provider="claude", data_dir=str(self.paths["claude"]),
            files=files, parse_file=counting_parse,
            parser_version=parser_version,
            bucket_set={_shared.bucket_id(b) for b in buckets},
            cache_root=self.cache_root,
        )

    def test_second_call_skips_parse(self):
        c = {"n": 0}
        self._aggregate("v1", c)
        self.assertGreater(c["n"], 0)
        n1 = c["n"]
        self._aggregate("v1", c)
        self.assertEqual(c["n"], n1, "fingerprint 命中应跳过 parse")

    def test_mtime_change_invalidates_entry(self):
        c = {"n": 0}
        self._aggregate("v1", c)
        n1 = c["n"]
        # 改文件让 mtime_ns 前进
        for fp in (self.paths["claude"]).glob("*.jsonl"):
            ns = (datetime.now().timestamp() + 60) * 1e9
            os.utime(fp, ns=(int(ns), int(ns)))
        self._aggregate("v1", c)
        self.assertGreater(c["n"], n1, "mtime 变化必须触发重 parse")

    def test_parser_version_invalidates_all(self):
        c = {"n": 0}
        self._aggregate("v1", c)
        n1 = c["n"]
        self._aggregate("v2", c)
        self.assertGreater(c["n"], n1, "parser_version 变化整份失效")

    def test_corrupt_cache_recovers(self):
        c = {"n": 0}
        self._aggregate("v1", c)
        # 写脏 cache（非 dict 内容）
        cache_path = _shared.cache_file_path("claude", str(self.paths["claude"]),
                                              root=self.cache_root)
        cache_path.write_text("[]", encoding="utf-8")
        self._aggregate("v1", c)
        # 不应抛异常；脏 cache 当首次处理
        self.assertGreater(c["n"], 0)

    def test_tz_offset_corruption_degrades(self):
        c = {"n": 0}
        self._aggregate("v1", c)
        cache_path = _shared.cache_file_path("claude", str(self.paths["claude"]),
                                              root=self.cache_root)
        with open(cache_path, "r+", encoding="utf-8") as fh:
            cache = json.load(fh)
            cache["tzOffsetSeconds"] = "not-a-number"
            fh.seek(0); fh.truncate()
            json.dump(cache, fh)
        # 必须不抛 ValueError，整份 cache 当无效
        self._aggregate("v1", c)

    def test_period_widening_reuses_old_entries(self):
        """7d 刷过后切到 30d，旧 file fingerprint 仍在 cache 里复用，不应整份失效。"""
        c = {"n": 0}
        # 先按 7d cutoff 跑
        buckets_7 = _today_buckets(7)
        files_7 = _shared.list_claude_files(str(self.paths["claude"]),
                                             _shared.mtime_cutoff(buckets_7[0]))
        def cp(fp): c["n"] += 1; return _shared.parse_claude_file(fp)
        _shared.aggregate_with_cache(
            provider="claude", data_dir=str(self.paths["claude"]),
            files=files_7, parse_file=cp,
            parser_version="v1",
            bucket_set={_shared.bucket_id(b) for b in buckets_7},
            cache_root=self.cache_root)
        n1 = c["n"]
        # 切 30d 跑
        buckets_30 = _today_buckets(30)
        files_30 = _shared.list_claude_files(str(self.paths["claude"]),
                                              _shared.mtime_cutoff(buckets_30[0]))
        _shared.aggregate_with_cache(
            provider="claude", data_dir=str(self.paths["claude"]),
            files=files_30, parse_file=cp,
            parser_version="v1",
            bucket_set={_shared.bucket_id(b) for b in buckets_30},
            cache_root=self.cache_root)
        # 同一文件已在 cache，应该不重新 parse
        self.assertEqual(c["n"], n1, "30d 复用 7d 已 parse 的 entry")

    def test_parse_failure_drops_stale_entry(self):
        """parse_file 抛异常时不应保留上一次的 stale 数据。"""
        c = {"n": 0}
        # 第一次正常 parse
        self._aggregate("v1", c)
        # 改 mtime 让 fingerprint 变化（强制本次重 parse）
        for fp in (self.paths["claude"]).glob("*.jsonl"):
            ns = (datetime.now().timestamp() + 60) * 1e9
            os.utime(fp, ns=(int(ns), int(ns)))
        # parse_file 抛异常
        buckets = _today_buckets(7)
        files = _shared.list_claude_files(str(self.paths["claude"]),
                                          _shared.mtime_cutoff(buckets[0]))
        def boom(_fp): raise RuntimeError("boom")
        by_bucket, totals = _shared.aggregate_with_cache(
            provider="claude", data_dir=str(self.paths["claude"]),
            files=files, parse_file=boom, parser_version="v1",
            bucket_set={_shared.bucket_id(b) for b in buckets},
            cache_root=self.cache_root)
        # stale entry 已被删除 → 输出聚合应空
        self.assertEqual(totals, {}, "parse 失败必须不返回 stale token")

    def test_corrupt_files_field_degrades(self):
        """cache 顶层元数据合规但 files 字段污染时不应崩。"""
        c = {"n": 0}
        self._aggregate("v1", c)
        cache_path = _shared.cache_file_path("claude", str(self.paths["claude"]),
                                              root=self.cache_root)
        for bad_files in (None, [], "string", {"x": "not-a-dict"},
                          {"x": {"fingerprint": "wrong-type", "byBucket": {}}},
                          {"x": {"fingerprint": {}, "byBucket": "not-dict"}}):
            with open(cache_path, "r+", encoding="utf-8") as fh:
                cache = json.load(fh)
                cache["files"] = bad_files
                fh.seek(0); fh.truncate()
                json.dump(cache, fh)
            # 不应抛
            self._aggregate("v1", c)

    def test_empty_byBucket_preserves_fingerprint(self):
        """所有桶被 prune 后 entry 仍保留（fingerprint 防 reparse）。"""
        c = {"n": 0}
        self._aggregate("v1", c)
        n1 = c["n"]
        # 把 cache 中的 byBucket 全清空，模拟所有桶都被 prune 掉
        cache_path = _shared.cache_file_path("claude", str(self.paths["claude"]),
                                              root=self.cache_root)
        with open(cache_path, "r+", encoding="utf-8") as fh:
            cache = json.load(fh)
            for k in cache["files"]:
                cache["files"][k]["byBucket"] = {}
            fh.seek(0); fh.truncate()
            json.dump(cache, fh)
        # 再跑：fingerprint 没变，应跳过 parse
        self._aggregate("v1", c)
        self.assertEqual(c["n"], n1, "空 byBucket entry 应保留以避免 reparse")

    def test_cache_root_failure_degrades(self):
        """cache_root 不可创建时 cache_file_path 返回 None，aggregate 全量 parse 不写盘。"""
        bogus = Path("/nonexistent-readonly-12345/xx")
        c = {"n": 0}
        buckets = _today_buckets(7)
        files = _shared.list_claude_files(str(self.paths["claude"]),
                                          _shared.mtime_cutoff(buckets[0]))
        def cp(fp): c["n"] += 1; return _shared.parse_claude_file(fp)
        _shared.aggregate_with_cache(
            provider="claude", data_dir=str(self.paths["claude"]),
            files=files, parse_file=cp,
            parser_version="v1",
            bucket_set={_shared.bucket_id(b) for b in buckets},
            cache_root=bogus)
        self.assertGreater(c["n"], 0)


# ──────────────────────────── plugin e2e tests ──────────────────────────────

class PluginEndToEndTests(unittest.TestCase):
    """跑真实 plugin（subprocess），HOME 隔离 + 临时 fixture，验证 stdout JSON shape。"""

    @classmethod
    def setUpClass(cls):
        cls.scratch = Path(tempfile.mkdtemp(prefix="tokenused-e2e-"))
        cls.paths = gen_fixtures(cls.scratch / "data")
        # 隔离 HOME → ~/Library/Caches 落到 scratch/home 下
        cls.fake_home = cls.scratch / "home"
        (cls.fake_home / "Library" / "Caches").mkdir(parents=True)
        cls.env = {**os.environ, "HOME": str(cls.fake_home)}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.scratch, ignore_errors=True)

    def _run(self, plugin: str, params: list[str]) -> dict:
        cmd = [sys.executable, str(PLUGINS / plugin), *params,
               "--usageboard-param", "USAGEBOARD_LANGUAGE=en"]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=30, env=self.env)
        self.assertEqual(proc.returncode, 0, msg=f"stderr={proc.stderr}")
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            self.fail(f"invalid JSON: {e}; head={proc.stdout[:300]}")

    def test_claude(self):
        out = self._run("claude-code-usage-plugin.py", [
            "--usageboard-param", f"DATA_DIR={self.paths['claude']}",
            "--usageboard-param", "STAT_PERIOD=7d",
        ])
        self.assertEqual(out["schemaVersion"], 1)
        self.assertEqual(len(out["items"]), 1)
        self.assertIn("trailingText", out["items"][0])
        self.assertEqual(len(out["chart"]["buckets"]), 7)

    def test_gemini(self):
        out = self._run("gemini-cli-usage-plugin.py", [
            "--usageboard-param", f"DATA_DIR={self.paths['gemini']}",
            "--usageboard-param", "STAT_PERIOD=7d",
        ])
        self.assertEqual(out["schemaVersion"], 1)
        self.assertEqual(len(out["items"]), 1)
        self.assertEqual(len(out["chart"]["buckets"]), 7)

    def test_codex(self):
        out = self._run("codex-local-usage-plugin.py", [
            "--usageboard-param", f"DATA_DIR={self.paths['codex']}",
            "--usageboard-param", "STAT_PERIOD=7d",
        ])
        self.assertEqual(out["schemaVersion"], 1)
        self.assertEqual(len(out["items"]), 1)

    def test_daily_overview(self):
        out = self._run("daily-overview-plugin.py", [
            "--usageboard-param", f"CLAUDE_DIR={self.paths['claude']}",
            "--usageboard-param", f"GEMINI_DIR={self.paths['gemini']}",
            "--usageboard-param", f"CODEX_DIR={self.paths['codex']}",
            "--usageboard-param", "CHART_PERIOD=7d",
        ])
        self.assertEqual(out["schemaVersion"], 1)
        self.assertEqual(len(out["chart"]["buckets"]), 7)
        # 三家都有今日 token，所以 hero + 至少 3 个 model 行
        self.assertGreaterEqual(len(out["items"]), 4)
        # 验 hero 有 trailingText（i18n 输出）
        self.assertIn("trailingText", out["items"][0])

    def test_daily_overview_handles_missing_provider_dir(self):
        """某 provider 目录不存在不应让整个 daily-overview 崩。"""
        out = self._run("daily-overview-plugin.py", [
            "--usageboard-param", f"CLAUDE_DIR={self.paths['claude']}",
            "--usageboard-param", "GEMINI_DIR=/nonexistent/path/xx",
            "--usageboard-param", f"CODEX_DIR={self.paths['codex']}",
            "--usageboard-param", "CHART_PERIOD=7d",
        ])
        self.assertEqual(out["schemaVersion"], 1)
        self.assertGreater(len(out["items"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
