"""
Helper script to detect total pages and calculate page ranges for parallel scraping.
"""
import json
import sys
import requests
from bs4 import BeautifulSoup

USED_CARS_URL = "https://www.motorgy.com/ar/used-cars"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
}


def get_total_pages():
    """Fetch the first page and extract total page count."""
    resp = requests.get(f"{USED_CARS_URL}?pn=1", headers=DEFAULT_HEADERS, timeout=30)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, "lxml")
    
    # Try to get from hidden fields first
    count_all = soup.select_one("#hdncountAll")
    count_from = soup.select_one("#hdncountFrom")
    count_to = soup.select_one("#hdncountTo")
    
    if count_all and count_from and count_to:
        try:
            total = int(count_all.get("value", 0))
            start = int(count_from.get("value", 0))
            end = int(count_to.get("value", 0))
            per_page = max(1, end - start + 1)
            if total > 0:
                return (total + per_page - 1) // per_page
        except (ValueError, TypeError):
            pass
    
    # Fallback: parse pagination div
    paging_div = soup.select_one("#pagingDiv")
    if paging_div:
        # Find all page number links
        import re
        pn_values = []
        for link in paging_div.select("a[href*='pn=']"):
            href = link.get("href", "")
            match = re.search(r"pn=(\d+)", href)
            if match:
                pn_values.append(int(match.group(1)))
        
        if pn_values:
            return max(pn_values)
    
    return None


def calculate_ranges(total_pages, num_parts):
    """Calculate page ranges for splitting scraping into parts."""
    pages_per_part = total_pages // num_parts
    remainder = total_pages % num_parts
    
    ranges = []
    current_start = 1
    
    for part_num in range(1, num_parts + 1):
        # Distribute remainder pages to first few parts
        pages_in_this_part = pages_per_part + (1 if part_num <= remainder else 0)
        current_end = current_start + pages_in_this_part - 1
        
        ranges.append({
            "part": part_num,
            "start_page": current_start,
            "end_page": current_end,
            "total_pages_in_part": pages_in_this_part
        })
        
        current_start = current_end + 1
    
    return ranges


def main():
    num_parts = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    
    print(f"Detecting total pages from {USED_CARS_URL}...", file=sys.stderr)
    total_pages = get_total_pages()
    
    if not total_pages:
        print("ERROR: Could not detect total pages", file=sys.stderr)
        sys.exit(1)
    
    print(f"Total pages detected: {total_pages}", file=sys.stderr)
    print(f"Dividing into {num_parts} parts...", file=sys.stderr)
    
    ranges = calculate_ranges(total_pages, num_parts)
    
    # Print summary to stderr
    for r in ranges:
        print(f"  Part {r['part']}: Pages {r['start_page']}-{r['end_page']} ({r['total_pages_in_part']} pages)", file=sys.stderr)
    
    # Output JSON to stdout for GitHub Actions
    output = {
        "total_pages": total_pages,
        "num_parts": num_parts,
        "ranges": ranges
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
