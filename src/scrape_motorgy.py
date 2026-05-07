import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import boto3
import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.motorgy.com"
USED_CARS_URL = "https://www.motorgy.com/ar/used-cars"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
}


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def get_env(name: str, required: bool = True, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_text(el) -> str:
    if not el:
        return ""
    return normalize_text(el.get_text(" ", strip=True))


def absolute_url(href: str) -> str:
    return urljoin(BASE_URL, href)


def parse_listing_page(html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for card in soup.select("div.car-card"):
        a = card.select_one("a[href*='/ar/car-details/']")
        if a and a.get("href"):
            links.append(absolute_url(a["href"]))
    return list(dict.fromkeys(links))


def parse_total_pages(html: str) -> Optional[int]:
    soup = BeautifulSoup(html, "lxml")

    count_all = soup.select_one("#hdncountAll")
    count_from = soup.select_one("#hdncountFrom")
    count_to = soup.select_one("#hdncountTo")
    try:
        total = int(count_all["value"]) if count_all and count_all.get("value") else 0
        start = int(count_from["value"]) if count_from and count_from.get("value") else 0
        end = int(count_to["value"]) if count_to and count_to.get("value") else 0
        per_page = max(1, end - start + 1)
        if total > 0:
            return (total + per_page - 1) // per_page
    except (ValueError, TypeError, KeyError):
        pass

    paging = soup.select_one("#pagingDiv")
    if paging:
        pn_values = [int(m.group(1)) for m in re.finditer(r"pn=(\d+)", str(paging))]
        if pn_values:
            return max(pn_values)

    return None


def parse_price_block(soup: BeautifulSoup) -> Tuple[str, str]:
    price = ""
    monthly = ""
    side_box = soup.select_one(".side-box")
    if side_box:
        price_el = side_box.select_one("h4")
        price = extract_text(price_el)
        monthly_el = side_box.select_one(".side p.fs-12")
        monthly = extract_text(monthly_el)
    return price, monthly


def parse_specs(soup: BeautifulSoup) -> Dict[str, str]:
    specs = {}
    for row in soup.select("#_specefication .data-table__row"):
        key = extract_text(row.select_one("p"))
        value = extract_text(row.select_one("span"))
        if key:
            specs[key] = value
    return specs


def parse_features(soup: BeautifulSoup) -> Dict[str, List[str]]:
    features: Dict[str, List[str]] = {}
    for item in soup.select("#_features .accordion-item"):
        section_title = extract_text(item.select_one(".accordion-button"))
        if not section_title:
            continue
        items = [
            extract_text(p)
            for p in item.select(".features-table__row p")
            if extract_text(p)
        ]
        if items:
            features[section_title] = items
    return features


def parse_inspection(soup: BeautifulSoup) -> Tuple[str, str, Dict[str, Dict[str, str]]]:
    date_text = ""
    summary_text = ""
    report: Dict[str, Dict[str, str]] = {}
    inspection = soup.select_one("#_inspection")
    if inspection:
        descriptions = [
            extract_text(p) for p in inspection.select(".pack-box__side .description")
        ]
        if descriptions:
            date_text = descriptions[0]
            if len(descriptions) > 1:
                summary_text = " ".join(descriptions[1:])
        for item in inspection.select(".accordion-item"):
            section_title = extract_text(item.select_one(".accordion-button"))
            if not section_title:
                continue
            section_data: Dict[str, str] = {}
            for row in item.select(".accordion-body > div"):
                label = extract_text(row.select_one("span.color_subtitle"))
                img = row.select_one("img")
                if not label or not img:
                    continue
                src = img.get("src", "")
                if "2020823123832523.png" in src:
                    section_data[label] = "yes"
            if section_data:
                report[section_title] = section_data
    return date_text, summary_text, report


def parse_description(soup: BeautifulSoup) -> str:
    return extract_text(soup.select_one("#_description .description"))


def parse_seller_phone(soup: BeautifulSoup) -> str:
    """Extract seller phone number from the call button."""
    phone = ""
    # Look for the call button with tel: href
    call_button = soup.select_one("a.btnCall[href^='tel:']")
    if call_button:
        href = call_button.get("href", "")
        # Extract phone number from tel:60057204 format
        phone = href.replace("tel:", "").strip()
    return phone


def parse_basic_info(soup: BeautifulSoup) -> Tuple[str, str, str]:
    title = extract_text(soup.select_one(".side-box h5"))
    year = ""
    mileage = ""
    model = soup.select_one(".side-box .car-model")
    if model:
        year = extract_text(model.select_one(".highlight"))
        spans = model.find_all("span")
        if len(spans) > 1:
            mileage = extract_text(spans[1])
    return title, year, mileage


def extract_image_urls(soup: BeautifulSoup) -> List[str]:
    urls = set()
    for slide in soup.select(".slider-box .swiper-slide"):
        for attr in ("data-src", "data-background"):
            val = slide.get(attr)
            if val:
                urls.add(val)
        style = slide.get("style", "")
        match = re.search(r"background-image:\s*url\([\"']?(.*?)[\"']?\)", style)
        if match:
            urls.add(match.group(1))
    for thumb in soup.select(".details-group__thumbnails a[data-src]"):
        urls.add(thumb.get("data-src"))
    return [u for u in urls if u]


def parse_ad_id(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    last = path.split("/")[-1]
    return re.sub(r"\D", "", last) or last


def file_extension_from_url(url: str) -> str:
    path = urlparse(url).path
    ext = os.path.splitext(path)[1]
    return ext if ext else ".jpg"


def slugify_column(text: str) -> str:
    text = normalize_text(text)
    text = re.sub(r"[\s/]+", "_", text)
    text = re.sub(r"[^\w\u0600-\u06FF_]+", "", text, flags=re.UNICODE)
    return text.strip("_")


def download_image(session: requests.Session, url: str) -> bytes:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content


def upload_bytes_to_s3(s3_client, bucket: str, key: str, content: bytes, content_type: str = "image/jpeg"):
    s3_client.put_object(Bucket=bucket, Key=key, Body=content, ContentType=content_type)


def scrape_detail(session: requests.Session, url: str) -> Dict[str, object]:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    title, year, mileage = parse_basic_info(soup)
    price, monthly = parse_price_block(soup)
    specs = parse_specs(soup)
    features = parse_features(soup)
    inspection_date, inspection_summary, inspection_report = parse_inspection(soup)
    description = parse_description(soup)
    seller_phone = parse_seller_phone(soup)
    images = extract_image_urls(soup)

    return {
        "title": title,
        "year": year,
        "mileage": mileage,
        "price": price,
        "monthly_estimate": monthly,
        "seller_phone_number": seller_phone,
        "specs": specs,
        "features": features,
        "inspection_date": inspection_date,
        "inspection_summary": inspection_summary,
        "inspection_report": inspection_report,
        "description": description,
        "image_urls": images,
    }


def scrape_all() -> None:
    bucket = get_env("S3_BUCKET")
    run_date = datetime.utcnow()
    year = run_date.strftime("%Y")
    month = run_date.strftime("%m")
    day = run_date.strftime("%d")
    part_label = get_env("PART_LABEL", required=False, default=None)
    s3_prefix = f"motorgy/year={year}/month={month}/day={day}"
    if part_label:
        s3_prefix = f"{s3_prefix}/part={part_label}"
    max_pages_env = get_env("MAX_PAGES", required=False, default=None)
    max_pages = int(max_pages_env) if max_pages_env else None
    start_page_env = get_env("START_PAGE", required=False, default=None)
    end_page_env = get_env("END_PAGE", required=False, default=None)
    start_page = int(start_page_env) if start_page_env else 1
    end_page = int(end_page_env) if end_page_env else None
    delay_seconds = float(get_env("REQUEST_DELAY_SECONDS", required=False, default="1.0"))

    print("Starting Motorgy scrape...")
    logger.info("Run date (UTC): %s-%s-%s", year, month, day)
    logger.info(
        "Max pages: %s | Start page: %s | End page: %s | Part: %s | Delay seconds: %s",
        max_pages or "ALL",
        start_page,
        end_page or "AUTO",
        part_label or "none",
        delay_seconds,
    )

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=get_env("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=get_env("AWS_SECRET_ACCESS_KEY"),
        region_name="us-east-1",
    )

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    all_links: List[str] = []
    page = 1
    first_page_url = f"{USED_CARS_URL}?pn=1"
    first_resp = session.get(first_page_url, timeout=30)
    if first_resp.status_code != 200:
        logger.error("Failed to load first page: %s (status %s)", first_page_url, first_resp.status_code)
        return

    total_pages = parse_total_pages(first_resp.text) or 1
    if max_pages:
        total_pages = min(total_pages, max_pages)
    if end_page:
        total_pages = min(total_pages, end_page)
    if start_page < 1:
        start_page = 1
    if start_page > total_pages:
        logger.warning("Start page (%s) exceeds total pages (%s). Nothing to do.", start_page, total_pages)
        return
    print(f"Total pages detected: {total_pages}")
    logger.info("Total pages detected: %s", total_pages)

    if start_page <= 1:
        first_links = parse_listing_page(first_resp.text)
        all_links.extend(first_links)
        logger.info("Page 1 links: %s", len(first_links))

    page = max(2, start_page)
    while page <= total_pages:
        page_url = f"{USED_CARS_URL}?pn={page}"
        resp = session.get(page_url, timeout=30)
        if resp.status_code != 200:
            logger.warning("Failed page %s: %s (status %s)", page, page_url, resp.status_code)
            break
        links = parse_listing_page(resp.text)
        if not links:
            logger.warning("No links found on page %s", page)
            break
        new_links = [l for l in links if l not in all_links]
        if not new_links:
            page += 1
            time.sleep(delay_seconds)
            continue
        all_links.extend(new_links)
        logger.info("Page %s new links: %s", page, len(new_links))
        page += 1
        time.sleep(delay_seconds)

    logger.info("Total unique ads: %s", len(all_links))

    results: List[Dict[str, object]] = []
    for idx, detail_url in enumerate(all_links, start=1):
        logger.info("Scraping ad %s/%s: %s", idx, len(all_links), detail_url)
        ad_id = parse_ad_id(detail_url)
        try:
            data = scrape_detail(session, detail_url)
        except Exception as exc:
            logger.warning("Failed to scrape detail %s: %s", detail_url, exc)
            continue
        image_urls = data.pop("image_urls", [])

        s3_image_paths = []
        for img_index, img_url in enumerate(image_urls, start=1):
            try:
                ext = file_extension_from_url(img_url)
                filename = f"{img_index:02d}{ext}"
                key = f"{s3_prefix}/images/{ad_id}/{filename}"
                content = download_image(session, img_url)
                content_type = "image/jpeg"
                if ext.lower() in {".png"}:
                    content_type = "image/png"
                upload_bytes_to_s3(s3_client, bucket, key, content, content_type)
                s3_image_paths.append(f"s3://{bucket}/{key}")
            except Exception as exc:
                logger.warning("Image upload failed (%s): %s", img_url, exc)
                continue

        row = {
            "ad_id": ad_id,
            "detail_url": detail_url,
            **data,
            "specs_json": json.dumps(data.get("specs", {}), ensure_ascii=False),
            "features_json": json.dumps(data.get("features", {}), ensure_ascii=False),
            "inspection_report_json": json.dumps(data.get("inspection_report", {}), ensure_ascii=False),
            "s3_images_paths": json.dumps(s3_image_paths, ensure_ascii=False),
            "images_count": len(s3_image_paths),
        }

        inspection_report = data.get("inspection_report", {}) or {}
        for section_name, items in inspection_report.items():
            section_key = slugify_column(section_name)
            for item_name, value in items.items():
                item_key = slugify_column(item_name)
                col_name = f"inspection_{section_key}__{item_key}"
                row[col_name] = value
        results.append(row)

        if idx % 10 == 0:
            logger.info("Progress: %s/%s ads", idx, len(all_links))

        if idx % 5 == 0:
            time.sleep(delay_seconds)

    df = pd.DataFrame(results)
    output_dir = os.path.join(os.getcwd(), "output")
    os.makedirs(output_dir, exist_ok=True)
    timestamp = run_date.strftime("%Y%m%d")
    part_suffix = f"_part-{part_label}" if part_label else ""
    excel_name = f"motorgy_used_cars_{timestamp}{part_suffix}.xlsx"
    excel_path = os.path.join(output_dir, excel_name)
    df.to_excel(excel_path, index=False)
    print(f"Excel saved: {excel_path}")
    logger.info("Excel saved: %s", excel_path)

    excel_key = f"{s3_prefix}/excel_files/{excel_name}"
    s3_client.upload_file(excel_path, bucket, excel_key)
    logger.info("Excel uploaded to s3://%s/%s", bucket, excel_key)
    print("Scrape complete.")


if __name__ == "__main__":
    scrape_all()
