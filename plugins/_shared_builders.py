"""Output builders for TokenUsed UsageBoard plugin JSON."""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable

from _shared_cache import merge_bucket_maps
from _shared_core import fmt_tokens, period_chart_buckets, tr
from _shared_parsers import scan_claude, scan_codex, scan_gemini

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


def _model_item_name(model: str) -> str:
    provider = _overview_provider_label(model)
    display = _overview_model_display(model, provider)
    prefix = f"{provider} · " if provider else ""
    return f"{prefix}{display}"


def _model_usage_item(*, item_id: str, model: str, tokens: int,
                      total: int, language: str) -> dict[str, Any]:
    total_m = total / 1_000_000
    tokens_m = tokens / 1_000_000
    return {
        "id": item_id,
        "name": _model_item_name(model),
        "used": tokens_m,
        "limit": max(total_m, 0.01),
        "displayStyle": "percent",
        "resetAt": None,
        "status": "normal", "color": "blue",
        "trailingText": fmt_tokens(tokens, language),
    }


OVERVIEW_PROVIDER_NAMES = {"claude": "Claude", "gemini": "Gemini", "codex": "Codex"}

PROVIDER_ICONS = {
    "claude": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/claude.png",
    "gemini": "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/gemini.png",
    "codex":  "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/openai.png",
}


def top_provider_icon(provider_totals: dict[str, int]) -> str | None:
    top = max(provider_totals, key=provider_totals.get) if provider_totals else None
    if top and provider_totals.get(top, 0) > 0:
        return PROVIDER_ICONS.get(top)
    return None


# 非额度行不带告警/品牌色语义，统一中性蓝，避免红橙被误读
def _provider_usage_item(*, provider: str, tokens: int, total: int,
                         language: str) -> dict[str, Any]:
    total_m = total / 1_000_000
    tokens_m = tokens / 1_000_000
    return {
        "id": f"overview-provider-{provider}",
        "name": OVERVIEW_PROVIDER_NAMES.get(provider, provider.capitalize()),
        "used": tokens_m,
        "limit": max(total_m, 0.01),
        "displayStyle": "percent",
        "resetAt": None,
        "status": "normal", "color": "blue",
        "trailingText": fmt_tokens(tokens, language),
    }


def build_per_cli_dimension(*, scan_fn: Callable, data_dir: str, period: str,
                             mode: str, language: str, hero_id_prefix: str
                             ) -> dict[str, Any]:
    by_bucket, model_totals, chart_meta, unit = scan_fn(data_dir, period, mode=mode)
    p_label = period_label(period, language)

    total = int(sum(model_totals.values()))
    total_m = total / 1_000_000

    items: list[dict[str, Any]] = []
    if total > 0:
        items.append({
            "id": f"{hero_id_prefix}-total",
            "name": tr(language, "total_tokens_for_period").format(period=p_label),
            "used": total_m, "limit": max(total_m, 0.01),
            "displayStyle": "ratio",
            "resetAt": None,
            "status": "normal", "color": "blue",
            "trailingText": fmt_tokens(total, language),
        })
        for i, (model, tokens) in enumerate(sorted(model_totals.items(), key=lambda kv: -kv[1])):
            items.append(_model_usage_item(
                item_id=f"{hero_id_prefix}-model-{i}-{model}",
                model=model,
                tokens=int(tokens),
                total=total,
                language=language,
            ))

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

    items: list[dict[str, Any]] = []
    if period_total > 0:
        sorted_providers = sorted(
            ((prov, tokens) for prov, tokens in provider_totals.items() if tokens > 0),
            key=lambda kv: -kv[1],
        )
        for prov, tokens in sorted_providers:
            items.append(_provider_usage_item(
                provider=prov, tokens=int(tokens),
                total=period_total, language=language,
            ))

    chart = _build_chart(by_bucket, period_model_totals, chart_meta, period, unit, language)
    if not any(b["segments"] for b in chart["buckets"]):
        chart["message"] = tr(language, "no_data")
    out = {"label": period_label(period, language), "bucketUnit": unit,
           "items": items, "chart": chart, "providerTotals": provider_totals}
    if period_total > 0:
        out["badge"] = fmt_tokens(period_total, language)
    icon_url = top_provider_icon(provider_totals)
    if icon_url:
        out["iconURL"] = icon_url
    return out
