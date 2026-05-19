"""
Enbik product catalog scraper.
Sources:
  https://enbik.com/product_category/ai-computer/
  https://enbik.com/product_category/rugged-computer/

For each product extracts: model, name, category, key features,
datasheet URL, product URL, and downloads all product images.
Output: products_enbik.csv + images/<model>_<n>.jpg
"""
import csv
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

CATEGORIES = {
    "ai-computer":     "https://enbik.com/product_category/ai-computer/",
    "rugged-computer": "https://enbik.com/product_category/rugged-computer/",
}

OUTPUT      = Path("products_enbik.csv")
IMAGE_DIR   = Path("images")
DELAY       = 1.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

FIELDNAMES = [
    "model", "name", "category", "features",
    "datasheet_url", "product_url", "images",
]


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://enbik.com/", timeout=15)   # pick up any session cookies
    return s


def get_product_urls(session: requests.Session, cat_slug: str, cat_url: str) -> set[str]:
    """Collect all /products/ URLs from a category and its subcategories."""
    urls: set[str] = set()

    def harvest(url: str) -> None:
        try:
            r = session.get(url, timeout=15)
            r.raise_for_status()
        except Exception as e:
            print(f"  WARN: could not fetch {url}: {e}", file=sys.stderr)
            return
        soup = BeautifulSoup(r.text, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "enbik.com/products/" in href:
                urls.add(href.split("?")[0].rstrip("/"))

    # Top-level page
    harvest(cat_url)

    # Subcategories one level deep
    r0 = session.get(cat_url, timeout=15)
    soup0 = BeautifulSoup(r0.text, "lxml")
    sub_links = set(
        a["href"] for a in soup0.find_all("a", href=True)
        if f"product_category/{cat_slug}/" in a["href"]
        and a["href"].startswith("http")
        and a["href"].rstrip("/") != cat_url.rstrip("/")
    )
    for sub in sub_links:
        harvest(sub)
        time.sleep(DELAY)

    return urls


def extract_model(name: str) -> str:
    """Extract the model number — everything before the first comma."""
    parts = name.split(",", 1)
    return parts[0].strip() if parts else name.strip()


def safe_filename(text: str) -> str:
    return re.sub(r"[^\w\-]", "_", text)


def download_image(session: requests.Session, url: str, dest: Path) -> bool:
    try:
        r = session.get(url, timeout=20, stream=True)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return True
    except Exception as e:
        print(f"  WARN: image download failed {url}: {e}", file=sys.stderr)
        return False


def parse_product(session: requests.Session, url: str, category: str) -> dict:
    r = session.get(url, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    main = soup.find("main") or soup

    # Product name (H1)
    h1 = main.find("h1")
    name = h1.get_text(strip=True) if h1 else ""
    model = extract_model(name)

    # Key features: bullet list directly under the H1 / in the summary block
    features_lines = []
    summary = (
        main.find(class_="woocommerce-product-details__short-description")
        or main.find(class_="entry-summary")
        or main.find(class_="product-short-description")
    )
    if summary:
        for li in summary.find_all("li"):
            text = li.get_text(strip=True)
            if text:
                features_lines.append(text)
    # Fallback: first <ul> with multiple <li> after the H1
    if not features_lines:
        for ul in main.find_all("ul"):
            items = [li.get_text(strip=True) for li in ul.find_all("li") if li.get_text(strip=True)]
            if len(items) >= 3:
                features_lines = items
                break
    features = " | ".join(features_lines)

    # Datasheet: first PDF link in the page
    datasheet_url = ""
    for a in main.find_all("a", href=True):
        if a["href"].lower().endswith(".pdf"):
            datasheet_url = a["href"]
            break

    # Product images: featured image + gallery
    image_urls: list[str] = []
    # WooCommerce gallery thumbnails
    for img in main.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        # Skip tiny thumbnails, icons, logos
        if not src or "logo" in src.lower() or "icon" in src.lower():
            continue
        # Prefer large images — skip 150x150 / 300x300 size suffixes
        if re.search(r"-\d+x\d+\.(jpg|png|webp)", src, re.I):
            continue
        if src.startswith("http") and any(
            ext in src.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]
        ):
            if src not in image_urls:
                image_urls.append(src)

    # Download images
    IMAGE_DIR.mkdir(exist_ok=True)
    model_slug = safe_filename(model)
    saved_files: list[str] = []
    for i, img_url in enumerate(image_urls[:8], 1):   # cap at 8 per product
        ext = Path(img_url.split("?")[0]).suffix or ".jpg"
        filename = f"{model_slug}_{i}{ext}"
        dest = IMAGE_DIR / filename
        if not dest.exists():
            if download_image(session, img_url, dest):
                saved_files.append(filename)
        else:
            saved_files.append(filename)

    return {
        "model":        model,
        "name":         name,
        "category":     category,
        "features":     features,
        "datasheet_url": datasheet_url,
        "product_url":  url,
        "images":       ", ".join(saved_files),
    }


def run() -> None:
    session = make_session()
    IMAGE_DIR.mkdir(exist_ok=True)

    # Phase 1: collect all product URLs per category
    all_products: dict[str, str] = {}   # url -> category
    for cat_slug, cat_url in CATEGORIES.items():
        print(f"Collecting product URLs from: {cat_slug}")
        urls = get_product_urls(session, cat_slug, cat_url)
        print(f"  Found {len(urls)} products")
        for u in urls:
            if u not in all_products:
                all_products[u] = cat_slug

    total = len(all_products)
    print(f"\nTotal unique products: {total}\n")

    # Phase 2: scrape each product page
    rows: list[dict] = []
    for i, (url, category) in enumerate(all_products.items(), 1):
        try:
            row = parse_product(session, url, category)
            rows.append(row)
            print(f"  [{i:>3}/{total}] {row['model']} ({category})")
        except Exception as e:
            print(f"  [{i:>3}/{total}] ERROR {url}: {e}", file=sys.stderr)
        time.sleep(DELAY)

    # Write CSV
    with OUTPUT.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone. {len(rows)} products -> {OUTPUT}")
    print(f"Images saved in: {IMAGE_DIR}/")


if __name__ == "__main__":
    run()
