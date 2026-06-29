#!/usr/bin/env python3
"""Count all R2 objects under scraper/site prefixes (shared with Pro1-Os hub)."""

from __future__ import annotations


def _normalize_prefix(prefix: str) -> str:
    normalized = prefix.strip("/")
    return f"{normalized}/" if normalized else ""


def _count_objects(client, bucket: str, prefix: str, label: str) -> int:
    """Paginate list_objects_v2 and count objects, excluding folder markers."""
    listing_prefix = _normalize_prefix(prefix)
    count = 0
    paginator = client.get_paginator("list_objects_v2")
    print(f"  Counting R2 objects under {listing_prefix or '(bucket root)'} ({label})...")
    for page in paginator.paginate(Bucket=bucket, Prefix=listing_prefix):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith("/"):
                continue
            count += 1
            if count % 10000 == 0:
                print(f"    ... {count:,} objects so far")
    print(f"  R2 file count ({label}): {count:,}")
    return count


def count_scraper_r2_files(client, bucket: str, r2_base: str) -> int:
    """Count every object under a scraper's R2 data prefix."""
    return _count_objects(client, bucket, r2_base, r2_base.strip("/") or "scraper")


def count_site_r2_files(client, bucket: str, r2_prefix: str) -> int:
    """Count every object under the site R2 prefix (includes monitor/ artifacts)."""
    return _count_objects(client, bucket, r2_prefix, r2_prefix.strip("/") or "site")
