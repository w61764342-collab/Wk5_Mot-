#!/usr/bin/env python3
"""Parse request metrics from JSON summaries for monitor report.json (shared with Pro1-Os hub)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from botocore.exceptions import ClientError

JSON_FOLDER_NAMES = ("json-files", "json_files")
TOTAL_KEYS = ("requests_total", "total_http_requests", "scrape_do_requests", "request_count")
FAILED_KEYS = ("requests_failed", "failed_requests", "http_errors", "errors_count")
DURATION_KEYS = ("duration_sec", "elapsed_seconds", "scrape_duration_sec")
RPM_KEYS = ("requests_per_min", "req_per_min", "avg_requests_per_min")
CACHE_KEYS = ("cache_hits",)


def _partition_prefix(base_path: str, partition_dt: datetime) -> str:
    return (
        f"{base_path.rstrip('/')}/year={partition_dt.strftime('%Y')}"
        f"/month={partition_dt.strftime('%m')}"
        f"/day={partition_dt.strftime('%d')}"
    )


def _first_int(data: dict, keys: Sequence[str]) -> Optional[int]:
    for key in keys:
        value = data.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return None


def _first_float(data: dict, keys: Sequence[str]) -> Optional[float]:
    for key in keys:
        value = data.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def _extract_metrics_block(data: dict) -> Dict[str, Any]:
    """Pull metrics from request_metrics, stats, or top-level aliases."""
    if not isinstance(data, dict):
        return {}

    sources: List[dict] = []
    request_metrics = data.get("request_metrics")
    if isinstance(request_metrics, dict):
        sources.append(request_metrics)
    stats = data.get("stats")
    if isinstance(stats, dict):
        sources.append(stats)
    sources.append(data)

    merged: Dict[str, Any] = {}
    for source in sources:
        if merged.get("requests_total") is None:
            value = _first_int(source, TOTAL_KEYS)
            if value is not None:
                merged["requests_total"] = value
        if merged.get("requests_failed") is None:
            value = _first_int(source, FAILED_KEYS)
            if value is not None:
                merged["requests_failed"] = value
        if merged.get("duration_sec") is None:
            value = _first_int(source, DURATION_KEYS)
            if value is not None:
                merged["duration_sec"] = value
        if merged.get("requests_per_min") is None:
            value = _first_float(source, RPM_KEYS)
            if value is not None:
                merged["requests_per_min"] = value
        if merged.get("cache_hits") is None:
            value = _first_int(source, CACHE_KEYS)
            if value is not None:
                merged["cache_hits"] = value
        if "failed_items" not in merged:
            failed_items = source.get("failed_items")
            if isinstance(failed_items, list) and failed_items:
                merged["failed_items"] = failed_items

    return merged


def _format_failed_items_summary(failed_items: Sequence[dict]) -> str:
    parts: List[str] = []
    for item in failed_items:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("slug") or "unknown"
        errors = item.get("errors", 1)
        detail = item.get("detail", "")
        suffix = f" ({detail})" if detail else ""
        parts.append(f"{name}: {errors} error(s){suffix}")
    return "; ".join(parts)


def _list_json_summaries(client, bucket: str, partition_prefix: str) -> List[dict]:
    """Find JSON summaries under json-files/ for a partition (including part= subfolders)."""
    summaries: List[dict] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{partition_prefix}/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.lower().endswith(".json"):
                continue
            if not any(f"/{folder}/" in key for folder in JSON_FOLDER_NAMES):
                continue
            try:
                body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
                data = json.loads(body)
            except (ClientError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(data, dict):
                summaries.append({"key": key, "data": data})
    return summaries


def _finalize_metrics(
    requests_total: int,
    requests_failed: int,
    duration_sec: Optional[int],
    cache_hits: int,
    failed_items: Sequence[dict],
    metrics_source: str,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "requests_total": requests_total,
        "requests_failed": requests_failed,
        "metrics_source": metrics_source,
    }
    if duration_sec is not None:
        result["duration_sec"] = duration_sec
    if cache_hits:
        result["cache_hits"] = cache_hits
    if requests_total > 0:
        result["error_rate_pct"] = round(requests_failed / requests_total * 100, 2)
    if duration_sec and duration_sec > 0:
        result["requests_per_min"] = round(requests_total / (duration_sec / 60), 2)
    if failed_items:
        result["failed_items_summary"] = _format_failed_items_summary(failed_items)
    return result


def _aggregate_metrics(metrics_list: Sequence[dict]) -> Dict[str, Any]:
    if not metrics_list:
        return {"metrics_source": "none"}

    requests_total = 0
    requests_failed = 0
    cache_hits = 0
    durations: List[int] = []
    failed_items: List[dict] = []

    for metrics in metrics_list:
        if metrics.get("requests_total") is not None:
            requests_total += int(metrics["requests_total"])
        if metrics.get("requests_failed") is not None:
            requests_failed += int(metrics["requests_failed"])
        if metrics.get("cache_hits") is not None:
            cache_hits += int(metrics["cache_hits"])
        if metrics.get("duration_sec") is not None:
            durations.append(int(metrics["duration_sec"]))
        items = metrics.get("failed_items") or []
        if isinstance(items, list):
            failed_items.extend(item for item in items if isinstance(item, dict))

    if not any(m.get("requests_total") is not None for m in metrics_list):
        return {"metrics_source": "none"}

    duration_sec = max(durations) if durations else None
    return _finalize_metrics(
        requests_total,
        requests_failed,
        duration_sec,
        cache_hits,
        failed_items,
        "json_summary",
    )


def count_scraper_request_metrics(
    r2_client,
    bucket: str,
    r2_base: str,
    partition_dt: datetime,
) -> Dict[str, Any]:
    """Return HTTP throughput/error metrics for one scraper partition."""
    partition_prefix = _partition_prefix(r2_base, partition_dt)
    summaries = _list_json_summaries(r2_client, bucket, partition_prefix)
    metrics_list = [
        block
        for block in (_extract_metrics_block(item["data"]) for item in summaries)
        if block.get("requests_total") is not None
    ]
    return _aggregate_metrics(metrics_list)


def aggregate_site_request_metrics(all_results: Sequence[dict]) -> Dict[str, Any]:
    """Roll up per-scraper request metrics to site-level totals."""
    requests_total = 0
    requests_failed = 0
    durations: List[int] = []
    found = False

    for result in all_results:
        total = result.get("requests_total")
        failed = result.get("requests_failed")
        if total is not None:
            requests_total += int(total)
            found = True
        if failed is not None:
            requests_failed += int(failed)
        duration = result.get("duration_sec")
        if duration is not None:
            durations.append(int(duration))

    if not found:
        return {}

    duration_sec = max(durations) if durations else None
    return _finalize_metrics(
        requests_total,
        requests_failed,
        duration_sec,
        0,
        [],
        "json_summary",
    )


def build_run_error_summary(
    all_results: Sequence[dict],
    alerts: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    """Build site-level error_summary for report.json."""
    del alerts  # reserved for future alert hooks

    scrapers = list(all_results)
    scrapers_total = len(scrapers)
    scrapers_passed = 0
    failed_scrapers: List[dict] = []

    for result in scrapers:
        name = result.get("scraper") or result.get("name") or "unknown"
        if result.get("all_passed", True):
            scrapers_passed += 1
            continue

        reason = "validation failed"
        if result.get("files_found", 0) == 0:
            reason = "no Excel files"

        failed_scrapers.append(
            {
                "scraper": name,
                "reason": reason,
                "requests_failed": result.get("requests_failed"),
            }
        )

    checks_total = sum(int(r.get("checks_total") or 0) for r in scrapers)
    checks_passed = sum(int(r.get("checks_passed") or 0) for r in scrapers)
    failed_checks = max(0, checks_total - checks_passed)
    validation_fail_rate_pct = (
        round(failed_checks / checks_total * 100, 2) if checks_total else 0.0
    )

    site_http = aggregate_site_request_metrics(scrapers)
    return {
        "scrapers_total": scrapers_total,
        "scrapers_failed": scrapers_total - scrapers_passed,
        "scrapers_passed": scrapers_passed,
        "validation_fail_rate_pct": validation_fail_rate_pct,
        "failed_scrapers": failed_scrapers,
        "http": {
            "requests_total": site_http.get("requests_total"),
            "requests_failed": site_http.get("requests_failed"),
            "error_rate_pct": site_http.get("error_rate_pct"),
            "requests_per_min": site_http.get("requests_per_min"),
        },
    }
