# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Enbik-Scrapper** — scrapes the Enbik Technology product catalog from two categories:
- `https://enbik.com/product_category/ai-computer/`
- `https://enbik.com/product_category/rugged-computer/`

Outputs a CSV with model, name, category, key features, datasheet URL, product URL, and image filenames. Downloads all product images to `images/`.

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```
python scraper_enbik.py
```

Output: `products_enbik.csv` + `images/<MODEL>_<n>.ext`

## Architecture

Single-file scraper (`scraper_enbik.py`). Two-phase approach:

1. **URL collection** — visits each top-level category page, then all subcategory pages one level deep, collecting all `/products/` links. Uses a `requests.Session` initialized with a homepage visit to pick up cookies.

2. **Product scraping** — for each product URL fetches the page, extracts:
   - Model number (text before the first comma in H1)
   - Full name (H1)
   - Key features (bullet list from `woocommerce-product-details__short-description`, or first `<ul>` with 3+ items)
   - Datasheet URL (first `.pdf` link on the page)
   - Product images (all `<img>` tags, excluding thumbnails with size suffixes like `-150x150`, capped at 8 per product)

Images are saved as `images/<MODEL>_<n>.<ext>`. Existing files are not re-downloaded.

**Note:** Country names in the Enbik shop are in Chinese (Traditional) — the site is Taiwan-based. Product names and specs are in English.
