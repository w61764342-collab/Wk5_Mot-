#!/usr/bin/env python3
"""Count unique ads for monitor report.json (shared with Pro1-Os hub)."""

from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd
from botocore.exceptions import ClientError

SKIP_SHEETS = {"info", "no data"}
ID_COLUMN_ALIASES = (
    "id",
    "listing_id",
    "listing id",
    "user_adv_id",
    "user adv id",
    "ad_id",
    "ad id",
)
COUNT_KEYS = ("total_listings", "total_ads", "listings_count")
JSON_FOLDER_NAMES = ("json-files", "json_files")


def _normalize_col(name: Any) -> str:
    return str(name).strip().lower().replace(" ", "_")


def _find_id_column(columns: Sequence[Any]) -> Optional[str]:
    normalized = {_normalize_col(col): col for col in columns}
    for alias in ID_COLUMN_ALIASES:
        key = _normalize_col(alias)
        if key in normalized:
            return str(normalized[key])
    return None


def _partition_prefix(base_path: str, partition_dt: datetime) -> str:
    return (
        f"{base_path.rstrip('/')}/year={partition_dt.strftime('%Y')}"
        f"/month={partition_dt.strftime('%m')}"
        f"/day={partition_dt.strftime('%d')}"
    )


def _count_from_excel(excel_downloads: Sequence[Tuple[str, bytes]]) -> Tuple[set, int]:
    all_ids: set = set()
    total_rows = 0

    for _key, content in excel_downloads:
        workbook = pd.ExcelFile(io.BytesIO(content))
        for sheet_name in workbook.sheet_names:
            if sheet_name.strip().lower() in SKIP_SHEETS:
                continue
            df = pd.read_excel(workbook, sheet_name=sheet_name)
            total_rows += len(df)
            id_col = _find_id_column(df.columns)
            if not id_col:
                continue
            ids = df[id_col].dropna().astype(str).str.strip()
            ids = ids[ids != ""]
            all_ids.update(ids.tolist())

    return all_ids, total_rows


def _count_rows_from_excel(excel_downloads: Sequence[Tuple[str, bytes]]) -> int:
    total_rows = 0
    for _key, content in excel_downloads:
        workbook = pd.ExcelFile(io.BytesIO(content))
        for sheet_name in workbook.sheet_names:
            if sheet_name.strip().lower() in SKIP_SHEETS:
                continue
            df = pd.read_excel(workbook, sheet_name=sheet_name)
            total_rows += len(df)
    return total_rows


def _extract_count_from_json(data: dict) -> Optional[int]:
    for key in COUNT_KEYS:
        value = data.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue

    subcategories = data.get("subcategories") or []
    if subcategories:
        subtotal = 0
        found = False
        for item in subcategories:
            count = item.get("listings_count")
            if count is not None:
                try:
                    subtotal += int(count)
                    found = True
                except (TypeError, ValueError):
                    continue
        if found:
            return subtotal
    return None


def _list_json_objects(client, bucket: str, prefix: str) -> List[dict]:
    objects: List[dict] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].lower().endswith(".json"):
                objects.append(obj)
    return objects


def _count_from_json_summaries(
    client,
    bucket: str,
    r2_base: str,
    partition_dt: datetime,
) -> Optional[int]:
    partition_prefix = _partition_prefix(r2_base, partition_dt)
    total = 0
    found_any = False

    for folder_name in JSON_FOLDER_NAMES:
        json_prefix = f"{partition_prefix}/{folder_name}/"
        try:
            json_objects = _list_json_objects(client, bucket, json_prefix)
        except (ClientError, AttributeError):
            continue
        for obj in json_objects:
            try:
                body = client.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read()
                data = json.loads(body)
            except (ClientError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            count = _extract_count_from_json(data if isinstance(data, dict) else {})
            if count is not None:
                total += count
                found_any = True

    return total if found_any else None


def count_scraper_ads(
    r2_client,
    bucket: str,
    r2_base: str,
    partition_dt: datetime,
    excel_downloads: Sequence[Tuple[str, bytes]],
) -> Dict[str, Any]:
    """Return unique ad counts for one scraper partition."""
    all_ids, excel_total_rows = _count_from_excel(excel_downloads)
    if all_ids:
        return {
            "unique_ads": len(all_ids),
            "total_rows": excel_total_rows,
            "ads_source": "excel_ids",
        }

    json_count = _count_from_json_summaries(r2_client, bucket, r2_base, partition_dt)
    if json_count is not None:
        return {
            "unique_ads": json_count,
            "total_rows": json_count,
            "ads_source": "json_summary",
        }

    if excel_downloads:
        row_count = _count_rows_from_excel(excel_downloads)
        if row_count > 0:
            return {
                "unique_ads": row_count,
                "total_rows": row_count,
                "ads_source": "excel_rows",
            }

    return {
        "unique_ads": 0,
        "total_rows": 0,
        "ads_source": "none",
    }
