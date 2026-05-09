"""Output builders for TokenUsed UsageBoard plugin JSON."""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable

from _shared_cache import merge_bucket_maps
from _shared_core import fmt_tokens, period_chart_buckets, tr
from _shared_parsers import scan_claude, scan_codex, scan_gemini

OVERVIEW_VISIBLE_MODELS = 5


def period_label(period: str, language: str) -> str:
    key = {"today": "period_today", "7d": "period_7d", "30d": "period_30d",
           "90d": "period_90d", "all": "period_all"}.get(period, "period_7d")
    return tr(language, key)


def _build_chart(by_bucket, model_totals, chart_meta, period, unit, language):
    sorted_models = [m for m, _ in sorted(model_totals.items(), key=lambda x: -x[1])]
    chart_buckets = []
    for meta in chart_meta:
        bid = meta["id"]
        segs = [
            {"model": m, "tokens": int(by_bucket.get(bid, {}).get(m, 0))}
            for m in sorted_models if by_bucket.get(bid, {}).get(m, 0) > 0
        ]
        chart_buckets.append({
            "id": bid, "label": meta["label"],
            "start": meta["start"], "end": meta["end"],
            "segments": segs,
        })
    msg = None if any(b["segments"] for b in chart_buckets) else tr(language, "no_data")
    return {"kind": "line", "period": period, "bucketUnit": unit,
            "buckets": chart_buckets, "message": msg}


def _token_mode_text(mode: str, language: str) -> str:
    mode_label = tr(language, "mode_billable" if mode == "billable" else "mode_raw")
    return f"{tr(language, 'token_mode')}: {mode_label}"


def _overview_provider_label(model: str) -> str | None:
    m = model.lower()
    if m.startswith("claude-"):
        return "Claude"
    if m.startswith("gemini-"):
        return "Gemini"
    if m.startswith(("glm-", "zhipu-")):
        return "GLM"
    if m.startswith(("gpt-", "o1", "o3", "o4", "openai-", "chatgpt-")):
        return "OpenAI"
    if m.startswith("codex-") or "-codex" in m:
        return "Codex"
    return None


def _overview_model_display(model: str, provider: str | None) -> str:
    display = model
    if provider == "Claude" and display.lower().startswith("claude-"):
        display = display[len("claude-"):]
    elif provider == "Gemini" and display.lower().startswith("gemini-"):
        display = display[len("gemini-"):]
    elif provider == "OpenAI" and display.lower().startswith("openai-"):
        display = display[len("openai-"):]
    elif provider == "GLM" and display.lower().startswith("zhipu-"):
        display = display[len("zhipu-"):]
    return " ".join(part.capitalize() for part in display.replace("_", "-").split("-") if part)


def _overview_item_name(model: str, tokens: int, language: str) -> str:
    provider = _overview_provider_label(model)
    display = _overview_model_display(model, provider)
    prefix = f"{provider} · " if provider else ""
    return f"{prefix}{display}  ({fmt_tokens(tokens, language)})"


def _other_models_label(count: int, language: str) -> str:
    key = "other_model" if count == 1 else "other_models"
    return tr(language, key).format(count=count)


def build_per_cli_dimension(*, scan_fn: Callable, data_dir: str, period: str,
                             mode: str, language: str, hero_id_prefix: str
                             ) -> dict[str, Any]:
    by_bucket, model_totals, chart_meta, unit = scan_fn(data_dir, period, mode=mode)
    p_label = period_label(period, language)
    mode_text = _token_mode_text(mode, language)

    total = int(sum(model_totals.values()))
    today_id = chart_meta[-1]["id"] if chart_meta else None
    today_total = int(sum(by_bucket.get(today_id, {}).values())) if today_id else 0
    peak_total = int(max((sum(v.values()) for v in by_bucket.values()), default=0))
    today_m = round(today_total / 1_000_000, 2)
    peak_m = round(peak_total / 1_000_000, 2)
    ratio = (today_total / peak_total) if peak_total > 0 else 0
    status = "critical" if ratio >= 1.0 else "warning" if ratio >= 0.8 else "normal"
    color = "red" if ratio >= 1.0 else "orange" if ratio >= 0.8 else "blue"

    items: list[dict[str, Any]] = []
    if total > 0:
        items.append({
            "id": f"{hero_id_prefix}-total",
            "name": f"{p_label} · {mode_text} · {fmt_tokens(total, language)} tokens",
            "used": today_m, "limit": max(peak_m, 0.01),
            "displayStyle": "ratio",
            "resetAt": None,
            "status": status, "color": color,
            "trailingText": fmt_tokens(today_total, language),
        })

    chart = _build_chart(by_bucket, model_totals, chart_meta, period, unit, language)
    return {"label": p_label, "bucketUnit": unit, "items": items, "chart": chart}


def build_overview_dimension(*, claude_dir: str, gemini_dir: str, codex_dir: str,
                              period: str, mode: str, language: str
                              ) -> dict[str, Any]:
    chart_meta, unit = period_chart_buckets(period, today=datetime.now().astimezone().date())
    by_bucket: dict[str, dict[str, int]] = {b["id"]: {} for b in chart_meta}
    provider_totals: dict[str, int] = {}

    def _run(scan_fn, data_dir):
        return scan_fn(data_dir, period, mode=mode)

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {
            "claude": ex.submit(_run, scan_claude, claude_dir),
            "gemini": ex.submit(_run, scan_gemini, gemini_dir),
            "codex":  ex.submit(_run, scan_codex,  codex_dir),
        }
        for prov, fut in futures.items():
            try:
                sub_by_bucket, _totals, _meta, _unit = fut.result()
            except Exception as exc:
                print(f"[daily-overview] scan_{prov} failed: {exc}", file=sys.stderr)
                continue
            provider_totals[prov] = int(sum(_totals.values()))
            merge_bucket_maps(by_bucket, sub_by_bucket)

    period_model_totals: dict[str, int] = {}
    for models in by_bucket.values():
        for m, t in models.items():
            period_model_totals[m] = period_model_totals.get(m, 0) + int(t)
    period_total = sum(period_model_totals.values())
    sorted_models = sorted(period_model_totals.items(), key=lambda kv: -kv[1])

    items: list[dict[str, Any]] = []
    if period_total > 0:
        total_m = round(period_total / 1_000_000, 2)
        p_label = period_label(period, language)
        mode_text = _token_mode_text(mode, language)
        items.append({
            "id": "overview-period-total",
            "name": f"{p_label}  ▸  {fmt_tokens(period_total, language)} tokens · {mode_text}",
            "used": total_m, "limit": max(total_m, 0.01),
            "displayStyle": "ratio",
            "resetAt": None,
            "status": "normal", "color": "blue",
            "trailingText": fmt_tokens(period_total, language),
        })
        visible_models = sorted_models[:OVERVIEW_VISIBLE_MODELS]
        for i, (model, tokens) in enumerate(visible_models):
            tokens_m = round(tokens / 1_000_000, 2)
            share = tokens / period_total if period_total else 0
            color = "red" if share >= 0.5 else "orange" if share >= 0.25 else "blue"
            items.append({
                "id": f"overview-{i}-{model}",
                "name": _overview_item_name(model, tokens, language),
                "used": tokens_m, "limit": max(total_m, 0.01),
                "displayStyle": "percent",
                "resetAt": None,
                "status": "normal", "color": color,
                "trailingText": fmt_tokens(tokens, language),
            })
        other_models = sorted_models[OVERVIEW_VISIBLE_MODELS:]
        if other_models:
            other_tokens = int(sum(tokens for _model, tokens in other_models))
            other_count = len(other_models)
            tokens_m = round(other_tokens / 1_000_000, 2)
            share = other_tokens / period_total if period_total else 0
            color = "red" if share >= 0.5 else "orange" if share >= 0.25 else "blue"
            items.append({
                "id": "overview-other-models",
                "name": f"{_other_models_label(other_count, language)}  ({fmt_tokens(other_tokens, language)})",
                "used": tokens_m, "limit": max(total_m, 0.01),
                "displayStyle": "percent",
                "resetAt": None,
                "status": "normal", "color": color,
                "trailingText": fmt_tokens(other_tokens, language),
            })

    chart = _build_chart(by_bucket, period_model_totals, chart_meta, period, unit, language)
    if not any(b["segments"] for b in chart["buckets"]):
        chart["message"] = tr(language, "no_data")
    return {"label": period_label(period, language), "bucketUnit": unit,
            "items": items, "chart": chart, "providerTotals": provider_totals}
