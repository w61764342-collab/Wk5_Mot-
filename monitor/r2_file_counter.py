#!/usr/bin/env python3
"""Count all R2 objects under scraper/site prefixes (shared with Pro1-Os hub)."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable


def _normalize_prefix(prefix: str) -> str:
    normalized = prefix.strip("/")
    return f"{normalized}/" if normalized else ""


def _count_objects_and_size(client, bucket: str, prefix: str, label: str) -> dict:
    """Paginate list_objects_v2 and aggregate object count + byte size."""
    listing_prefix = _normalize_prefix(prefix)
    count = 0
    size_bytes = 0
    paginator = client.get_paginator("list_objects_v2")
    print(f"  Counting R2 objects under {listing_prefix or '(bucket root)'} ({label})...")
    for page in paginator.paginate(Bucket=bucket, Prefix=listing_prefix):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith("/"):
                continue
            count += 1
            size_bytes += int(obj.get("Size", 0) or 0)
            if count % 10000 == 0:
                print(f"    ... {count:,} objects so far")
    print(
        f"  R2 usage ({label}): {count:,} files, "
        f"{size_bytes:,} bytes"
    )
    return {"file_count": count, "size_bytes": size_bytes}


def count_scraper_r2_usage(client, bucket: str, r2_base: str) -> dict:
    """Return cumulative file count and bytes under a scraper's R2 data prefix."""
    return _count_objects_and_size(client, bucket, r2_base, r2_base.strip("/") or "scraper")


def count_site_r2_usage(client, bucket: str, r2_prefix: str) -> dict:
    """Return cumulative file count and bytes under the site R2 prefix."""
    return _count_objects_and_size(client, bucket, r2_prefix, r2_prefix.strip("/") or "site")


def _date_partition_prefix(base_path: str, target_date: datetime) -> str:
    normalized = base_path.strip("/")
    return (
        f"{normalized}/year={target_date.strftime('%Y')}"
        f"/month={target_date.strftime('%m')}"
        f"/day={target_date.strftime('%d')}"
    )


def _sum_daily_usage(client, bucket: str, base_path: str, dates: Iterable[datetime], label: str) -> dict:
    file_count = 0
    size_bytes = 0
    for day in dates:
        prefix = _date_partition_prefix(base_path, day)
        usage = _count_objects_and_size(client, bucket, prefix, f"{label} {day.strftime('%Y-%m-%d')}")
        file_count += int(usage.get("file_count", 0))
        size_bytes += int(usage.get("size_bytes", 0))
    return {"file_count": file_count, "size_bytes": size_bytes}


def count_scraper_r2_daily_usage(
    client, bucket: str, r2_base: str, dates: Iterable[datetime]
) -> dict:
    """Return file count and bytes under date partition prefix(es) for a scraper."""
    return _sum_daily_usage(
        client,
        bucket,
        r2_base,
        dates,
        r2_base.strip("/") or "scraper",
    )


def count_site_r2_daily_usage(
    client, bucket: str, r2_prefix: str, dates: Iterable[datetime]
) -> dict:
    """Return file count and bytes under date partition prefix(es) for the site."""
    return _sum_daily_usage(
        client,
        bucket,
        r2_prefix,
        dates,
        r2_prefix.strip("/") or "site",
    )


def count_scraper_r2_files(client, bucket: str, r2_base: str) -> int:
    """Count every object under a scraper's R2 data prefix."""
    usage = count_scraper_r2_usage(client, bucket, r2_base)
    return int(usage.get("file_count", 0))


def count_site_r2_files(client, bucket: str, r2_prefix: str) -> int:
    """Count every object under the site R2 prefix (includes monitor/ artifacts)."""
    usage = count_site_r2_usage(client, bucket, r2_prefix)
    return int(usage.get("file_count", 0))
