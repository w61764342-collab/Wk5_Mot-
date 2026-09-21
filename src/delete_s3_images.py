#!/usr/bin/env python3
"""Delete Motorgy image objects already stored in AWS S3.

Targets keys under the site prefix that look like scrape image uploads:
  motorgy/year=…/month=…/day=…[/part=…]/images/{ad_id}/01.jpg

Excel artifacts are never deleted.
Dry-run is the default; pass --execute to actually delete.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable, List, Optional, Tuple

import boto3
from botocore.config import Config

DEFAULT_SITE_PREFIX = "motorgy"
IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".tiff",
    ".svg",
}
DELETE_BATCH_SIZE = 1000


def get_env(name: str, fallback: Optional[str] = None) -> str:
    value = os.getenv(name) or (os.getenv(fallback) if fallback else None)
    if not value:
        names = name if not fallback else f"{name} (or {fallback})"
        raise RuntimeError(f"Missing required environment variable: {names}")
    return value


def build_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=get_env("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=get_env("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1",
        config=Config(signature_version="s3v4"),
    )


def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def build_list_prefix(
    site_prefix: str,
    year: Optional[str] = None,
    month: Optional[str] = None,
    day: Optional[str] = None,
) -> str:
    parts = [site_prefix.strip("/")]
    if year:
        parts.append(f"year={year}")
    if month:
        if not year:
            raise ValueError("--month requires --year")
        parts.append(f"month={month.zfill(2)}")
    if day:
        if not year or not month:
            raise ValueError("--day requires --year and --month")
        parts.append(f"day={day.zfill(2)}")
    return "/".join(parts) + "/"


def is_image_object(key: str) -> bool:
    """True for scrape image keys under …/images/… with an image extension."""
    if key.endswith("/"):
        return False
    normalized = key.lower()
    if "/images/" not in normalized:
        return False
    # Never touch spreadsheet / json / monitor artifacts even if misnamed.
    protected_markers = (
        "/excel_files/",
        "/json-files/",
        "/json version/",
        "/monitor/",
    )
    if any(marker in normalized for marker in protected_markers):
        return False
    ext = os.path.splitext(normalized)[1]
    return ext in IMAGE_EXTENSIONS


def list_image_objects(
    client,
    bucket: str,
    prefix: str,
) -> List[Tuple[str, int]]:
    """Return (key, size) for Motorgy image objects under prefix."""
    found: List[Tuple[str, int]] = []
    paginator = client.get_paginator("list_objects_v2")
    print(f"Listing objects under s3://{bucket}/{prefix}")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if not is_image_object(key):
                continue
            size = int(obj.get("Size", 0) or 0)
            found.append((key, size))
            if len(found) % 5000 == 0:
                print(f"  … {len(found):,} image objects matched so far")
    return found


def chunked(items: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def delete_keys(client, bucket: str, keys: List[str]) -> Tuple[int, int]:
    """Batch-delete keys. Returns (deleted_count, error_count)."""
    deleted = 0
    errors = 0
    total = len(keys)
    for batch_num, batch in enumerate(chunked(keys, DELETE_BATCH_SIZE), start=1):
        response = client.delete_objects(
            Bucket=bucket,
            Delete={
                "Objects": [{"Key": key} for key in batch],
                "Quiet": True,
            },
        )
        batch_errors = response.get("Errors", []) or []
        batch_deleted = len(batch) - len(batch_errors)
        deleted += batch_deleted
        errors += len(batch_errors)
        for err in batch_errors:
            print(
                f"  ERROR deleting {err.get('Key')}: "
                f"{err.get('Code')} — {err.get('Message')}"
            )
        print(
            f"  Batch {batch_num}: deleted {batch_deleted}/{len(batch)} "
            f"(progress {min(batch_num * DELETE_BATCH_SIZE, total):,}/{total:,})"
        )
    return deleted, errors


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete Motorgy scrape images from AWS S3"
    )
    parser.add_argument(
        "--site-prefix",
        default=os.getenv("SITE_PREFIX", DEFAULT_SITE_PREFIX),
        help=f"Site S3 prefix (default: {DEFAULT_SITE_PREFIX})",
    )
    parser.add_argument("--year", default=os.getenv("YEAR") or None, help="Filter year=YYYY")
    parser.add_argument("--month", default=os.getenv("MONTH") or None, help="Filter month=MM")
    parser.add_argument("--day", default=os.getenv("DAY") or None, help="Filter day=DD")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete objects (default is dry-run)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=20,
        help="How many matching keys to print as a sample (default: 20)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    dry_run = not args.execute

    bucket = get_env("S3_BUCKET", fallback="S3_BUCKET_NAME")
    client = build_s3_client()
    prefix = build_list_prefix(args.site_prefix, args.year, args.month, args.day)

    mode = "DRY-RUN" if dry_run else "EXECUTE"
    print("=" * 60)
    print(f"Motorgy S3 image cleanup — {mode}")
    print(f"Bucket : {bucket}")
    print(f"Prefix : {prefix}")
    print("=" * 60)

    images = list_image_objects(client, bucket, prefix)
    total_bytes = sum(size for _, size in images)
    print(f"\nMatched {len(images):,} image object(s), {format_bytes(total_bytes)}")

    if not images:
        print("Nothing to delete.")
        return 0

    sample_n = max(0, args.sample)
    if sample_n:
        print(f"\nSample keys (up to {sample_n}):")
        for key, size in images[:sample_n]:
            print(f"  {key}  ({format_bytes(size)})")
        if len(images) > sample_n:
            print(f"  … and {len(images) - sample_n:,} more")

    if dry_run:
        print(
            "\nDry-run only — no objects deleted. "
            "Re-run with --execute to permanently delete these images."
        )
        return 0

    print(f"\nDeleting {len(images):,} image object(s)…")
    keys = [key for key, _ in images]
    deleted, errors = delete_keys(client, bucket, keys)
    print(f"\nDone. Deleted: {deleted:,} | Errors: {errors:,}")
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — top-level CLI exit
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
