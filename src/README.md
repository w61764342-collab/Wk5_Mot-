# Motorgy Used Cars Scraper

A comprehensive web scraper for [Motorgy](https://www.motorgy.com) used car listings that automatically collects vehicle data, downloads images, and stores everything in AWS S3. The scraper runs monthly via GitHub Actions with automatic page detection and parallel processing.

## 📋 Table of Contents
- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Data Collected](#data-collected)
- [S3 Storage Structure](#s3-storage-structure)
- [Setup](#setup)
- [Configuration](#configuration)
- [Running the Scraper](#running-the-scraper)
- [GitHub Actions Workflows](#github-actions-workflows)
- [Helper Scripts](#helper-scripts)
- [Troubleshooting](#troubleshooting)

## ✨ Features

- **Automatic Page Detection**: Dynamically detects total pages from website
- **Parallel Processing**: Splits scraping into multiple parts running simultaneously
- **Comprehensive Data Extraction**:
  - Basic info (title, year, mileage, price)
  - Seller contact (phone number)
  - Detailed specifications
  - Features and amenities
  - Inspection reports (when available)
  - Vehicle description
  - All listing images
- **Image Management**: Downloads and uploads all images to S3 with organized naming
- **Excel Export**: Generates structured Excel files with all data
- **S3 Integration**: Automatically uploads images and Excel files with partitioned structure
- **Scheduled Runs**: Monthly automatic execution on the 1st at 3 AM UTC
- **Flexible Configuration**: Customizable via environment variables

## 🏗️ Architecture

### Dynamic Workflow System
The scraper uses a two-phase approach:

1. **Detection Phase**: 
   - Fetches the first page of listings
   - Parses pagination to determine total pages (e.g., 150 pages)
   - Calculates equal page ranges for parallel processing
   
2. **Scraping Phase**:
   - Launches multiple parallel jobs (default: 4)
   - Each job scrapes its assigned page range independently
   - All jobs run simultaneously for maximum speed
   - Results are stored in S3 with unique part labels

### Performance
- **Sequential scraping**: ~4-5 hours (150 pages × ~2 min/page)
- **Parallel scraping (4 parts)**: ~1-1.5 hours (4 jobs running simultaneously)

## 📁 Project Structure

```
Project5-MOY/
├── .github/
│   └── workflows/
│       ├── scrape-monthly-dynamic.yml    # Main dynamic workflow
│       └── scrape-test.yml               # Test workflow
├── src/
│   ├── scrape_motorgy.py                 # Main scraper script
│   ├── get_page_ranges.py                # Page range calculator
│   └── README.md                         # Technical documentation
└── requirements.txt                      # Python dependencies
```

## 🔄 How It Works

### 1. Listing Discovery
```
https://www.motorgy.com/ar/used-cars?pn=1
https://www.motorgy.com/ar/used-cars?pn=2
...
https://www.motorgy.com/ar/used-cars?pn=150
```
- Scrapes each listing page
- Extracts detail page URLs for all vehicles
- Removes duplicates

### 2. Detail Page Scraping
For each vehicle detail page (e.g., `https://www.motorgy.com/ar/car-details/mazda-cx-5/59521`):
- **Basic Info**: Parses title, year, mileage from `.side-box`
- **Pricing**: Extracts price and monthly estimate
- **Seller Contact**: Gets phone number from call button `a.btnCall[href^='tel:']`
- **Specifications**: Parses data table (`#_specefication`)
- **Features**: Extracts all feature categories (`#_features`)
- **Inspection Report**: Parses inspection data when available (`#_inspection`)
- **Description**: Gets vehicle description text
- **Images**: Collects all image URLs from slider and thumbnails

### 3. Image Processing
- Downloads each image via HTTP request
- Uploads to S3 with naming: `<ad_id>/01.jpg`, `<ad_id>/02.jpg`, etc.
- Stores S3 URIs in JSON array for reference

### 4. Data Export
- Combines all data into pandas DataFrame
- Flattens inspection report into individual columns
- Exports to Excel with timestamp
- Uploads Excel file to S3

## 📊 Data Collected

### Core Columns
| Column | Description | Example |
|--------|-------------|---------|
| `ad_id` | Unique ad identifier | `59521` |
| `detail_url` | Full URL to detail page | `https://www.motorgy.com/ar/car-details/...` |
| `title` | Vehicle title | `مازدا cx-5` |
| `year` | Year of manufacture | `2018` |
| `mileage` | Odometer reading | `85,000 كم` |
| `price` | Listing price | `5,500 KD` |
| `monthly_estimate` | Monthly payment estimate | `157 KD شهريا` |
| `seller_phone_number` | Seller contact number | `60057204` |
| `description` | Vehicle description text | `...` |

### JSON Columns
| Column | Description |
|--------|-------------|
| `specs_json` | Full specifications as JSON string |
| `features_json` | All features organized by category |
| `inspection_report_json` | Complete inspection report |
| `s3_images_paths` | Array of S3 URIs for all images |

### Metadata Columns
| Column | Description |
|--------|-------------|
| `images_count` | Number of images uploaded |
| `inspection_date` | Date of inspection (if available) |
| `inspection_summary` | Summary text from inspection |

### Dynamic Inspection Columns
Inspection report items are flattened into individual columns with naming pattern:
```
inspection_<section>__<item>
```
Examples:
- `inspection_الهيكل_الخارجي__المصد_الأمامي`
- `inspection_المحرك__البطارية`
- `inspection_الداخلية__المقاعد`

## 🗂️ S3 Storage Structure

### Directory Layout
```
s3://<bucket>/motorgy/
└── year=2026/
    └── month=02/
        └── day=15/
            ├── part=1/
            │   ├── images/
            │   │   ├── 59521/
            │   │   │   ├── 01.jpg
            │   │   │   ├── 02.jpg
            │   │   │   └── ...
            │   │   └── 59522/
            │   │       └── ...
            │   └── excel_files/
            │       └── motorgy_used_cars_20260215_part-1.xlsx
            ├── part=2/
            │   └── ...
            ├── part=3/
            │   └── ...
            └── part=4/
                └── ...
```

### Partitioning Benefits
- **Time-based partitioning**: Easy to query specific months/days
- **Part-based partitioning**: Enables parallel uploads and processing
- **Ad-based image organization**: All images for one ad in same folder

## 🚀 Setup

### Prerequisites
- Python 3.11 or higher
- AWS account with S3 bucket
- GitHub account (for automated workflows)

### Local Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Project3-S0-Ex
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set environment variables**
   ```bash
   # Windows PowerShell
   $env:AWS_ACCESS_KEY_ID = "your-access-key"
   $env:AWS_SECRET_ACCESS_KEY = "your-secret-key"
   $env:S3_BUCKET = "your-bucket-name"
   
   # Linux/Mac
   export AWS_ACCESS_KEY_ID="your-access-key"
   export AWS_SECRET_ACCESS_KEY="your-secret-key"
   export S3_BUCKET="your-bucket-name"
   ```

### GitHub Actions Setup

1. **Add GitHub Secrets**
   - Go to repository Settings → Secrets and variables → Actions
   - Add the following secrets:
     - `AWS_ACCESS_KEY_ID`
     - `AWS_SECRET_ACCESS_KEY`
     - `S3_BUCKET_NAME`

2. **Enable GitHub Actions**
   - Go to repository Actions tab
   - Enable workflows if prompted

3. **Configure S3 Bucket**
   - Ensure bucket exists in `us-east-1` region
   - Set appropriate IAM permissions:
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [
         {
           "Effect": "Allow",
           "Action": [
             "s3:PutObject",
             "s3:GetObject"
           ],
           "Resource": "arn:aws:s3:::your-bucket-name/*"
         }
       ]
     }
     ```

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AWS_ACCESS_KEY_ID` | ✅ Yes | - | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | ✅ Yes | - | AWS secret key |
| `S3_BUCKET` | ✅ Yes | - | S3 bucket name |
| `START_PAGE` | ❌ No | `1` | First page to scrape |
| `END_PAGE` | ❌ No | Auto-detected | Last page to scrape |
| `MAX_PAGES` | ❌ No | All pages | Maximum pages to process |
| `PART_LABEL` | ❌ No | None | Label for this scraping part |
| `REQUEST_DELAY_SECONDS` | ❌ No | `1.0` | Delay between requests |

### Workflow Inputs

When running manually, you can specify:
- **num_parts**: Number of parallel parts (default: 4)

## 🏃 Running the Scraper

### Local Execution

**Full scrape:**
```bash
python src/scrape_motorgy.py
```

**Scrape specific pages:**
```bash
# Windows
$env:START_PAGE = "1"
$env:END_PAGE = "10"
python src/scrape_motorgy.py

# Linux/Mac
START_PAGE=1 END_PAGE=10 python src/scrape_motorgy.py
```

**Test with limited pages:**
```bash
# Windows
$env:MAX_PAGES = "5"
python src/scrape_motorgy.py

# Linux/Mac
MAX_PAGES=5 python src/scrape_motorgy.py
```

### GitHub Actions Execution

**Scheduled (Automatic):**
- Runs automatically on the 1st of every month at 3 AM UTC
- No action needed

**Manual Run:**
1. Go to Actions tab
2. Select "Scrape Motorgy Monthly (Dynamic)"
3. Click "Run workflow"
4. Optionally set number of parts (default: 4)
5. Click "Run workflow" button

## 🔧 GitHub Actions Workflows

### scrape-monthly-dynamic.yml (Main)
**Purpose**: Automatic monthly scraping with dynamic page detection

**Schedule**: `0 3 1 * *` (1st of month, 3 AM UTC)

**Process**:
1. **detect-pages** job:
   - Installs Python and dependencies
   - Runs `get_page_ranges.py` to detect total pages
   - Calculates page ranges for parallel processing
   - Outputs matrix configuration

2. **scrape** job (parallel):
   - Receives page range from matrix
   - Scrapes assigned pages
   - Uploads to S3 with part label
   - Runs independently of other parts

**Benefits**:
- Automatically adapts to changing total pages
- Fails gracefully (if part 2 fails, parts 1,3,4 continue)
- Provides detailed summary for each part

### scrape-test.yml
**Purpose**: Testing and development

**Trigger**: Manual only

**Configuration**: Can be customized for testing specific scenarios

## 🛠️ Helper Scripts

### get_page_ranges.py
**Purpose**: Calculate optimal page ranges for parallel scraping

**Usage**:
```bash
# Default: 4 parts
python src/get_page_ranges.py

# Custom number of parts
python src/get_page_ranges.py 6
```

**Output**:
```json
{
  "total_pages": 150,
  "num_parts": 4,
  "ranges": [
    {"part": 1, "start_page": 1, "end_page": 38, "total_pages_in_part": 38},
    {"part": 2, "start_page": 39, "end_page": 76, "total_pages_in_part": 38},
    {"part": 3, "start_page": 77, "end_page": 114, "total_pages_in_part": 38},
    {"part": 4, "start_page": 115, "end_page": 150, "total_pages_in_part": 36}
  ]
}
```

**Features**:
- Detects total pages from website
- Divides pages equally (distributes remainder to first parts)
- Outputs JSON for GitHub Actions matrix

## 🐛 Troubleshooting

### Common Issues

**"Failed to load first page"**
- Check internet connection
- Verify website is accessible
- Check if website structure changed

**"Image upload failed"**
- Check AWS credentials
- Verify S3 bucket permissions
- Ensure bucket exists in us-east-1

**"No links found on page X"**
- Website may have fewer pages than expected
- Check if scraper finished naturally
- Verify page structure hasn't changed

**Excel file not created**
- Check if any ads were scraped successfully
- Verify output directory permissions
- Check disk space

### Debugging

**Enable verbose logging:**
```bash
# Modify logging level in scrape_motorgy.py
logging.basicConfig(level=logging.DEBUG)
```

**Test with small sample:**
```bash
$env:MAX_PAGES = "2"
python src/scrape_motorgy.py
```

**Validate page detection:**
```bash
python src/get_page_ranges.py
```

### Website Changes

If data extraction fails, the website HTML structure may have changed. Update selectors in `scrape_motorgy.py`:

- **Phone number**: `parse_seller_phone()` - looks for `a.btnCall[href^='tel:']`
- **Price**: `parse_price_block()` - uses `.side-box h4`
- **Specifications**: `parse_specs()` - uses `#_specefication .data-table__row`
- **Features**: `parse_features()` - uses `#_features .accordion-item`
- **Images**: `extract_image_urls()` - uses `.slider-box .swiper-slide`

## 📝 Notes

- **Rate Limiting**: Default 1-second delay between requests to be respectful
- **Error Handling**: Failed images/ads are logged and skipped
- **Duplicates**: URLs are deduplicated before detail scraping
- **AWS Region**: Hardcoded to `us-east-1`
- **Excel Format**: Uses `.xlsx` format via pandas
- **Character Encoding**: Supports Arabic text (UTF-8)

## ⚖️ Disclaimer

This scraper is for educational and personal use. Please:
- Respect the website's terms of service
- Use reasonable rate limiting
- Do not overload the server
- Ensure you have permission to scrape and store the data
- Comply with applicable data protection laws

## 📄 License

[Add your license here]

## 🤝 Contributing

[Add contributing guidelines if applicable]

## 📧 Contact

[Add contact information if applicable]
