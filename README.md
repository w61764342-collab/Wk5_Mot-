# Motorgy Used Car Scraper

A small Python project that detects the total number of used car listing pages on Motorgy, splits the work into parallel scraping ranges, scrapes all listing detail pages, uploads images and results to Cloudflare R2, and exports the final data to Excel.

## Contents

- `CF/get_page_ranges.py` - Detects total pages and calculates split page ranges for parallel scraping.
- `CF/scrape_motorgy.py` - Main scraper that collects listing detail data, downloads images, uploads to Cloudflare R2, and saves results to Excel.
- `.github/workflows/scrape-monthly-dynamic-cf.yml` - GitHub Actions workflow that runs the scraper monthly and splits the work into multiple parallel jobs.
- `requirements.txt` - Python dependencies needed for the scraper.

## Features

- Dynamic detection of total listing pages on Motorgy
- Automatic page-range calculation for parallel scraping
- Scraping of vehicle details, price, seller phone, specs, features, inspections, descriptions, and images
- Uploads images and Excel output to Cloudflare R2
- Saves final data locally to `output/` as an Excel file
- Supports configurable start/end page, request delay, and part label via environment variables

## Setup

1. Create a Python virtual environment and activate it.

   Windows PowerShell:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

## Usage

### 1. Detect page ranges

Use `CF/get_page_ranges.py` to detect the total number of pages and calculate page ranges for parallel scraping.

```powershell
python CF/get_page_ranges.py 4
```

This prints a JSON object containing `total_pages`, `num_parts`, and `ranges`.

### 2. Run the scraper locally

Set the required Cloudflare R2 environment variables and optionally define page range or part label values.

Required env vars:
- `CF_R2_BUCKET_NAME`
- `CF_R2_ENDPOINT_URL`
- `CF_R2_ACCESS_KEY_ID`
- `CF_R2_SECRET_ACCESS_KEY`

Optional env vars:
- `START_PAGE` - First listing page to scrape (defaults to `1`)
- `END_PAGE` - Last listing page to scrape
- `PART_LABEL` - A label for the current scraping part
- `MAX_PAGES` - Maximum total pages to scrape
- `REQUEST_DELAY_SECONDS` - Delay between page requests (default `1.0`)

Example:

```powershell
$env:CF_R2_BUCKET_NAME = "your-bucket"
$env:CF_R2_ENDPOINT_URL = "https://<account>.r2.cloudflarestorage.com"
$env:CF_R2_ACCESS_KEY_ID = "YOUR_ACCESS_KEY"
$env:CF_R2_SECRET_ACCESS_KEY = "YOUR_SECRET_KEY"
$env:START_PAGE = "1"
$env:END_PAGE = "20"
$env:PART_LABEL = "part-1"
python CF/scrape_motorgy.py
```

The scraper saves an Excel file to the local `output/` directory and uploads the same file and images to Cloudflare R2.

## GitHub Actions

The workflow file `.github/workflows/scrape-monthly-dynamic-cf.yml` is configured to run monthly and uses a dynamic matrix approach:

1. Detect total pages via `CF/get_page_ranges.py`
2. Split the total pages into multiple parts
3. Run `CF/scrape_motorgy.py` in parallel for each page range

The workflow also supports manual dispatch with a `num_parts` input.

## Notes

- The script expects the Motorgy Arabic used cars page at `https://www.motorgy.com/ar/used-cars`.
- Excel output is generated using `pandas` and `openpyxl`.
- Image uploads are handled via `boto3` configured to use Cloudflare R2.

## Project Structure

```text
.
├── CF/
│   ├── get_page_ranges.py
│   └── scrape_motorgy.py
├── .github/
│   └── workflows/
│       └── scrape-monthly-dynamic-cf.yml
├── requirements.txt
└── README.md
```
