#!/usr/bin/env python3
"""
Generic Amazon search/product data extractor via SerpAPI.
Saves structured results to a configurable Supabase table.

Modes:
  --search_phrase  Keyword search (engine=amazon). Auto two-stage if product
                   sections are requested: extracts ASINs then calls
                   engine=amazon_product for each.
  --asin           Direct product lookup (engine=amazon_product).

Usage:
  python serpapi_amazon_search.py --search_phrase "weight loss supplements" \
    --sections "organic_results,reviews_information,about_item" \
    --table amazon_results \
    --supabase_url https://xxx.supabase.co \
    --supabase_key SERVICE_ROLE_KEY \
    [--run_id UUID] [--max_asins 10]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

SERPAPI_URL = "https://serpapi.com/search"

# Sections returned by engine=amazon (search term mode)
SEARCH_SECTIONS = {
    "organic_results",
    "featured_products",
    "product_ads",
    "related_searches",
    "sponsored_brands",
    "video_results",
}

# Sections returned by engine=amazon_product (ASIN mode or two-stage)
PRODUCT_SECTIONS = {
    "product_results",
    "reviews_information",
    "about_item",
    "product_features",
    "product_details",
    "item_specifications",
    "item_ingredients",
    "prices",
    "purchase_options",
    "bought_together",
    "compare_with_similar",
    "related_products",
    "other_sellers",
    "protection_plan",
    "sustainability_features",
    "product_description",
    "product_sponsored_brands",
    "product_videos",
    "similar_product_videos",
}

# Maps skill section names to actual SerpAPI response keys
PRODUCT_SECTION_KEY_MAP = {
    "product_sponsored_brands": "sponsored_brands",
    "product_videos": "videos",
}


def load_env():
    candidates = [
        Path("C:/Users/jeshj/Desktop/Coding/_scripts/_shared/.env"),
        Path(__file__).parent / ".env",
        Path.cwd() / ".env",
    ]
    for path in candidates:
        if path.exists():
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())
            return


def serpapi_get(api_key, params):
    try:
        import requests
    except ImportError:
        print("ERROR: requests library not installed. Run: pip install requests")
        sys.exit(1)

    params = {**params, "api_key": api_key}
    resp = requests.get(SERPAPI_URL, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def supabase_insert(supabase_url, secret_key, table, row):
    try:
        import requests
    except ImportError:
        print("ERROR: requests library not installed. Run: pip install requests")
        sys.exit(1)

    url = f"{supabase_url.rstrip('/')}/rest/v1/{table}"
    headers = {
        "apikey": secret_key,
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    resp = requests.post(url, headers=headers, json=row, timeout=30)
    resp.raise_for_status()


def search_amazon(api_key, phrase):
    return serpapi_get(api_key, {"engine": "amazon", "k": phrase})


def fetch_product(api_key, asin):
    return serpapi_get(api_key, {"engine": "amazon_product", "asin": asin})


def extract_asins_from_search(search_data):
    asins = []
    for item in search_data.get("organic_results", []):
        asin = item.get("asin")
        if asin and asin not in asins:
            asins.append(asin)
    return asins


def build_search_rows(phrase, search_data, requested_sections, run_id):
    rows = []
    for section in requested_sections:
        if section not in SEARCH_SECTIONS:
            continue
        section_data = search_data.get(section)
        if not section_data:
            continue

        if section == "organic_results":
            for item in section_data:
                rows.append({
                    "run_id": run_id,
                    "search_phrase": phrase,
                    "asin": item.get("asin"),
                    "mode": "search",
                    "source_section": section,
                    "title": item.get("title"),
                    "price": item.get("price"),
                    "extracted_price": item.get("extracted_price"),
                    "rating": item.get("rating"),
                    "reviews": item.get("reviews"),
                    "data": item,
                })
        elif section == "featured_products":
            for block in section_data:
                for item in block.get("products", []):
                    rows.append({
                        "run_id": run_id,
                        "search_phrase": phrase,
                        "asin": item.get("asin"),
                        "mode": "search",
                        "source_section": section,
                        "title": item.get("title"),
                        "price": item.get("price"),
                        "extracted_price": item.get("extracted_price"),
                        "rating": item.get("rating"),
                        "reviews": item.get("reviews"),
                        "data": {"block_title": block.get("title"), **item},
                    })
        elif section == "product_ads":
            for item in section_data.get("products", []):
                rows.append({
                    "run_id": run_id,
                    "search_phrase": phrase,
                    "asin": item.get("asin"),
                    "mode": "search",
                    "source_section": section,
                    "title": item.get("title"),
                    "price": item.get("price"),
                    "extracted_price": item.get("extracted_price"),
                    "rating": item.get("rating"),
                    "reviews": item.get("reviews"),
                    "data": item,
                })
        elif section == "related_searches":
            for item in section_data:
                rows.append({
                    "run_id": run_id,
                    "search_phrase": phrase,
                    "asin": None,
                    "mode": "search",
                    "source_section": section,
                    "title": item.get("query") or str(item),
                    "price": None,
                    "extracted_price": None,
                    "rating": None,
                    "reviews": None,
                    "data": item if isinstance(item, dict) else {"query": item},
                })
        elif section == "sponsored_brands":
            for brand in section_data.get("brands", []):
                rows.append({
                    "run_id": run_id,
                    "search_phrase": phrase,
                    "asin": None,
                    "mode": "search",
                    "source_section": section,
                    "title": brand.get("name"),
                    "price": None,
                    "extracted_price": None,
                    "rating": None,
                    "reviews": None,
                    "data": brand,
                })
        elif section == "video_results":
            for item in section_data:
                rows.append({
                    "run_id": run_id,
                    "search_phrase": phrase,
                    "asin": None,
                    "mode": "search",
                    "source_section": section,
                    "title": item.get("title"),
                    "price": None,
                    "extracted_price": None,
                    "rating": None,
                    "reviews": None,
                    "data": item,
                })

    return rows


def build_product_row(asin, product_data, requested_sections, run_id, search_phrase):
    merged_data = {}

    for section in requested_sections:
        if section not in PRODUCT_SECTIONS:
            continue
        api_key = PRODUCT_SECTION_KEY_MAP.get(section, section)
        section_val = product_data.get(api_key)
        if section_val is not None:
            merged_data[section] = section_val

    pr = product_data.get("product_results", {})
    return {
        "run_id": run_id,
        "search_phrase": search_phrase,
        "asin": asin,
        "mode": "product",
        "source_section": "product_api",
        "title": pr.get("title"),
        "price": pr.get("price"),
        "extracted_price": pr.get("extracted_price"),
        "rating": pr.get("rating"),
        "reviews": pr.get("reviews"),
        "data": merged_data,
    }


def main():
    parser = argparse.ArgumentParser(description="Amazon SerpAPI extractor")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--search_phrase", help="Keyword to search on Amazon")
    group.add_argument("--asin", help="Amazon ASIN for direct product lookup")
    parser.add_argument("--sections", required=True,
                        help="Comma-separated section names to fetch")
    parser.add_argument("--table", required=True,
                        help="Supabase table name to write results to")
    parser.add_argument("--supabase_url", required=True,
                        help="Supabase project URL")
    parser.add_argument("--supabase_key", required=True,
                        help="Supabase service role key")
    parser.add_argument("--run_id", default=None,
                        help="Optional run UUID for linking results")
    parser.add_argument("--max_asins", type=int, default=10,
                        help="Max ASINs to fetch in two-stage mode (default: 10)")
    args = parser.parse_args()

    load_env()

    serpapi_key = os.environ.get("SERPAPI_API_KEY")
    if not serpapi_key:
        print("ERROR: SERPAPI_API_KEY is not set in environment or .env file.")
        sys.exit(1)

    requested_sections = [s.strip() for s in args.sections.split(",") if s.strip()]
    unknown = [s for s in requested_sections
               if s not in SEARCH_SECTIONS and s not in PRODUCT_SECTIONS]
    if unknown:
        print(f"WARNING: Unknown sections will be ignored: {', '.join(unknown)}")
        requested_sections = [s for s in requested_sections if s not in unknown]

    has_product_sections = any(s in PRODUCT_SECTIONS for s in requested_sections)
    rows_saved = 0
    failed = 0

    if args.asin:
        # --- ASIN mode ---
        phrase_label = f"ASIN:{args.asin}"
        print(f"Fetching product page for ASIN {args.asin}...")
        try:
            product_data = fetch_product(serpapi_key, args.asin)
            row = build_product_row(
                args.asin, product_data, requested_sections,
                args.run_id, None
            )
            supabase_insert(args.supabase_url, args.supabase_key, args.table, row)
            rows_saved += 1
        except Exception as e:
            print(f"WARNING: Failed to fetch/save ASIN {args.asin}: {e}")
            failed += 1

        print(f"STATS:mode=asin,search_phrase={phrase_label},"
              f"products=1,rows_saved={rows_saved},failed={failed}")

    else:
        # --- Search Term mode ---
        phrase_label = args.search_phrase
        print(f"Searching Amazon for: {phrase_label}")
        try:
            search_data = search_amazon(serpapi_key, args.search_phrase)
        except Exception as e:
            print(f"ERROR: Amazon search failed: {e}")
            sys.exit(1)

        # Save search-level sections
        search_rows = build_search_rows(
            args.search_phrase, search_data, requested_sections, args.run_id
        )
        for row in search_rows:
            try:
                supabase_insert(
                    args.supabase_url, args.supabase_key, args.table, row
                )
                rows_saved += 1
            except Exception as e:
                print(f"WARNING: Failed to save search row: {e}")
                failed += 1

        products = len(search_data.get("organic_results", []))

        # Auto two-stage: fetch product data for each ASIN
        if has_product_sections:
            asins = extract_asins_from_search(search_data)[:args.max_asins]
            print(f"Fetching product data for {len(asins)} ASINs...")
            for asin in asins:
                try:
                    product_data = fetch_product(serpapi_key, asin)
                    row = build_product_row(
                        asin, product_data, requested_sections,
                        args.run_id, args.search_phrase
                    )
                    supabase_insert(
                        args.supabase_url, args.supabase_key, args.table, row
                    )
                    rows_saved += 1
                    time.sleep(0.3)
                except Exception as e:
                    print(f"WARNING: Failed to fetch/save ASIN {asin}: {e}")
                    failed += 1

        print(f"STATS:mode=search,search_phrase={phrase_label},"
              f"products={products},rows_saved={rows_saved},failed={failed}")


if __name__ == "__main__":
    main()
