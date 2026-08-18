#!/usr/bin/env python3
"""Count all R2 objects under scraper/site prefixes (shared with Pro1-Os hub)."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Iterable

FILE_CATEGORIES = ("images", "json", "excel", "csv", "parquet", "other")

EXTENSION_TO_CATEGORY = {
    ".jpg": "images",
    ".jpeg": "images",
    ".png": "images",
    ".webp": "images",
    ".gif": "images",
    ".bmp": "images",
    ".tiff": "images",
    ".svg": "images",
    ".json": "json",
    ".xlsx": "excel",
    ".xls": "excel",
    ".xlsm": "excel",
    ".csv": "csv",
    ".parquet": "parquet",
}


def _empty_by_type() -> dict[str, int]:
    return {category: 0 for category in FILE_CATEGORIES}


def _empty_inventory() -> dict:
    return {
        "objects": 0,
        "size_bytes": 0,
        "by_type_objects": _empty_by_type(),
        "by_type_bytes": _empty_by_type(),
    }


def _normalize_prefix(prefix: str) -> str:
    normalized = prefix.strip("/")
    return f"{normalized}/" if normalized else ""


def _categorize_object_key(key: str) -> str:
    ext = os.path.splitext(key)[1].lower()
    return EXTENSION_TO_CATEGORY.get(ext, "other")


def _merge_inventories(*inventories: dict) -> dict:
    merged = _empty_inventory()
    for inventory in inventories:
        merged["objects"] += int(inventory.get("objects", 0))
        merged["size_bytes"] += int(inventory.get("size_bytes", 0))
        for category in FILE_CATEGORIES:
            merged["by_type_objects"][category] += int(
                inventory.get("by_type_objects", {}).get(category, 0)
            )
            merged["by_type_bytes"][category] += int(
                inventory.get("by_type_bytes", {}).get(category, 0)
            )
    return merged


def _accumulate_object(inventory: dict, key: str, size_bytes: int) -> None:
    category = _categorize_object_key(key)
    inventory["objects"] += 1
    inventory["size_bytes"] += size_bytes
    inventory["by_type_objects"][category] += 1
    inventory["by_type_bytes"][category] += size_bytes


def count_r2_inventory_by_type(client, bucket: str, prefix: str, label: str = "") -> dict:
    """Paginate list_objects_v2 and aggregate inventory by file type."""
    listing_prefix = _normalize_prefix(prefix)
    inventory = _empty_inventory()
    paginator = client.get_paginator("list_objects_v2")
    display_label = label or listing_prefix or "(bucket root)"
    print(f"  Counting R2 objects under {listing_prefix or '(bucket root)'} ({display_label})...")
    for page in paginator.paginate(Bucket=bucket, Prefix=listing_prefix):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith("/"):
                continue
            size_bytes = int(obj.get("Size", 0) or 0)
            _accumulate_object(inventory, key, size_bytes)
            if inventory["objects"] % 10000 == 0:
                print(f"    ... {inventory['objects']:,} objects so far")
    print(
        f"  R2 usage ({display_label}): {inventory['objects']:,} files, "
        f"{inventory['size_bytes']:,} bytes"
    )
    return inventory


def _partition_prefix_variants(base_path: str, target_date: datetime) -> list[str]:
    normalized = base_path.strip("/")
    year = target_date.strftime("%Y")
    months = {target_date.strftime("%m"), str(target_date.month)}
    days = {target_date.strftime("%d"), str(target_date.day)}
    variants: list[str] = []
    for month in sorted(months):
        for day in sorted(days):
            variants.append(f"{normalized}/year={year}/month={month}/day={day}")
    return variants


def count_daily_r2_inventory_by_type(
    client, bucket: str, r2_base: str, partition_dt: datetime
) -> dict:
    """Return inventory for one partition day, deduping padded/unpadded prefixes."""
    seen_keys: set[str] = set()
    inventory = _empty_inventory()
    label = r2_base.strip("/") or "scraper"
    date_label = partition_dt.strftime("%Y-%m-%d")
    for prefix in _partition_prefix_variants(r2_base, partition_dt):
        listing_prefix = _normalize_prefix(prefix)
        paginator = client.get_paginator("list_objects_v2")
        print(
            f"  Counting R2 objects under {listing_prefix} "
            f"({label} {date_label})..."
        )
        for page in paginator.paginate(Bucket=bucket, Prefix=listing_prefix):
            for obj in page.get("Contents", []):
                key = obj.get("Key", "")
                if key.endswith("/"):
                    continue
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                size_bytes = int(obj.get("Size", 0) or 0)
                _accumulate_object(inventory, key, size_bytes)
                if inventory["objects"] % 10000 == 0:
                    print(f"    ... {inventory['objects']:,} objects so far")
    print(
        f"  R2 daily usage ({label} {date_label}): {inventory['objects']:,} files, "
        f"{inventory['size_bytes']:,} bytes"
    )
    return inventory


def count_scraper_r2_inventory_by_type(client, bucket: str, r2_base: str) -> dict:
    """Return cumulative inventory under a scraper's R2 data prefix."""
    label = r2_base.strip("/") or "scraper"
    return count_r2_inventory_by_type(client, bucket, r2_base, label)


def count_site_r2_inventory_by_type(client, bucket: str, r2_prefix: str) -> dict:
    """Return cumulative inventory under the site R2 prefix."""
    label = r2_prefix.strip("/") or "site"
    return count_r2_inventory_by_type(client, bucket, r2_prefix, label)


def count_scraper_r2_usage(client, bucket: str, r2_base: str) -> dict:
    """Return cumulative file count and bytes under a scraper's R2 data prefix."""
    inventory = count_scraper_r2_inventory_by_type(client, bucket, r2_base)
    return {"file_count": inventory["objects"], "size_bytes": inventory["size_bytes"]}


def count_site_r2_usage(client, bucket: str, r2_prefix: str) -> dict:
    """Return cumulative file count and bytes under the site R2 prefix."""
    inventory = count_site_r2_inventory_by_type(client, bucket, r2_prefix)
    return {"file_count": inventory["objects"], "size_bytes": inventory["size_bytes"]}


def sum_daily_r2_inventory_by_type(
    client, bucket: str, r2_base: str, dates: Iterable[datetime]
) -> dict:
    """Return merged daily inventory across one or more partition dates."""
    inventory = _empty_inventory()
    for day in dates:
        daily = count_daily_r2_inventory_by_type(client, bucket, r2_base, day)
        inventory = _merge_inventories(inventory, daily)
    return inventory


def count_scraper_r2_daily_usage(
    client, bucket: str, r2_base: str, dates: Iterable[datetime]
) -> dict:
    """Return file count and bytes under date partition prefix(es) for a scraper."""
    inventory = sum_daily_r2_inventory_by_type(client, bucket, r2_base, dates)
    return {"file_count": inventory["objects"], "size_bytes": inventory["size_bytes"]}


def count_site_r2_daily_usage(
    client, bucket: str, r2_prefix: str, dates: Iterable[datetime]
) -> dict:
    """Return file count and bytes under date partition prefix(es) for the site."""
    inventory = sum_daily_r2_inventory_by_type(client, bucket, r2_prefix, dates)
    return {"file_count": inventory["objects"], "size_bytes": inventory["size_bytes"]}


def count_scraper_r2_files(client, bucket: str, r2_base: str) -> int:
    """Count every object under a scraper's R2 data prefix."""
    usage = count_scraper_r2_usage(client, bucket, r2_base)
    return int(usage.get("file_count", 0))


def count_site_r2_files(client, bucket: str, r2_prefix: str) -> int:
    """Count every object under the site R2 prefix (includes monitor/ artifacts)."""
    usage = count_site_r2_usage(client, bucket, r2_prefix)
    return int(usage.get("file_count", 0))


def apply_type_bytes_fields(target: dict, inventory: dict, field_prefix: str) -> None:
    """Add flattened r2_*_bytes fields from an inventory dict."""
    by_type_bytes = inventory.get("by_type_bytes", {})
    target[f"{field_prefix}_images_bytes"] = int(by_type_bytes.get("images", 0))
    target[f"{field_prefix}_json_bytes"] = int(by_type_bytes.get("json", 0))
    target[f"{field_prefix}_excel_bytes"] = int(by_type_bytes.get("excel", 0))
    target[f"{field_prefix}_csv_bytes"] = int(by_type_bytes.get("csv", 0))
    target[f"{field_prefix}_parquet_bytes"] = int(by_type_bytes.get("parquet", 0))
    target[f"{field_prefix}_other_bytes"] = int(by_type_bytes.get("other", 0))
