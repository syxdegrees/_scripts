#!/usr/bin/env python3
"""
Amazon SerpAPI cache-first fetcher.

Checks Supabase for fresh data before calling the API.
Stores raw API sections as JSONB columns in intermediary tables.
Emits JSON lines + STATS to stdout for the calling skill.

Usage:
  python serpapi_amazon_search.py --search_phrase "espresso machine" --max_asins 10
  python serpapi_amazon_search.py --asin B09XXXXX
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

SERPAPI_URL = "https://serpapi.com/search"

VALID_DOMAINS = {
    "amazon.com", "amazon.co.uk", "amazon.ca", "amazon.de",
    "amazon.fr", "amazon.es", "amazon.it", "amazon.co.jp",
    "amazon.in", "amazon.com.au", "amazon.com.mx",
}

# Columns in serpapi_amazon_search_cache that hold API section data (nullable JSONB).
# Keys match both the SerpAPI response keys and the Supabase column names.
SEARCH_SECTION_COLS = {
    "search_information",
    "organic_results",
    "featured_products",
    "product_ads",
    "sponsored_brands",
    "video_results",
    "related_searches",
    "categories",
    "filters",
}

# Columns in serpapi_amazon_product_cache that hold API section data (nullable JSONB).
PRODUCT_SECTION_COLS = {
    "product_results",
    "purchase_options",
    "prices",
    "other_sellers",
    "protection_plan",
    "about_item",
    "item_specifications",
    "item_ingredients",
    "product_details",
    "product_description",
    "product_features",
    "reviews_information",
    "bought_together",
    "related_products",
    "compare_with_similar",
    "videos",
    "similar_product_videos",
    "sustainability_features",
    "sponsored_brands",
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


def search_amazon(api_key, phrase, country="amazon.com", page=1):
    return serpapi_get(api_key, {
        "engine": "amazon",
        "k": phrase,
        "amazon_domain": country,
        "page": page,
    })


def fetch_product(api_key, asin, country="amazon.com"):
    return serpapi_get(api_key, {
        "engine": "amazon_product",
        "asin": asin,
        "amazon_domain": country,
    })


def clean_search_term(term: str) -> str:
    term = term.lower().strip()
    term = re.sub(r"\s+", "-", term)
    term = re.sub(r"[^a-z0-9-]", "", term)
    term = re.sub(r"-+", "-", term)
    return term.strip("-")


def get_supabase_config():
    """Load Supabase creds from environment. Call load_env() first."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url:
        print("ERROR: SUPABASE_URL not found in environment or .env")
        sys.exit(1)
    if not key:
        print("ERROR: SUPABASE_SECRET_KEY not found in environment or .env")
        sys.exit(1)
    return {"url": url.rstrip("/"), "key": key}


def _supabase_headers(config):
    return {
        "apikey": config["key"],
        "Authorization": f"Bearer {config['key']}",
        "Content-Type": "application/json",
    }


def _supabase_get(config, table, params):
    """GET rows from Supabase REST API. Returns list of row dicts."""
    try:
        import requests
    except ImportError:
        print("ERROR: requests library not installed. Run: pip install requests")
        sys.exit(1)
    url = f"{config['url']}/rest/v1/{table}"
    headers = {**_supabase_headers(config), "Accept": "application/json"}
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _supabase_post(config, table, row):
    """INSERT a row into Supabase REST API. Returns inserted row dict (with id)."""
    try:
        import requests
    except ImportError:
        print("ERROR: requests library not installed. Run: pip install requests")
        sys.exit(1)
    url = f"{config['url']}/rest/v1/{table}"
    headers = {**_supabase_headers(config), "Prefer": "return=representation"}
    resp = requests.post(url, headers=headers, json=row, timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else {}


_SERPAPI_META_KEYS = {"search_metadata", "search_parameters", "serpapi_pagination"}


def strip_serpapi_metadata(response: dict) -> dict:
    """Return a copy of response with SerpAPI housekeeping keys removed."""
    return {k: v for k, v in response.items() if k not in _SERPAPI_META_KEYS}


def extract_top_asins(organic_results: list, max_asins: int) -> list:
    """
    Return list of (position, asin) tuples from organic_results.
    position = original index in organic_results (0-based).
    Skips items without an 'asin' key. Returns at most max_asins items.
    """
    result = []
    for i, item in enumerate(organic_results):
        asin = item.get("asin")
        if asin:
            result.append((i, asin))
        if len(result) == max_asins:
            break
    return result


def _ttl_cutoff(ttl_days: int) -> str:
    """ISO 8601 timestamp for the oldest acceptable fetched_at."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    return cutoff.isoformat()


def cache_lookup_search(config, search_phrase, country, pages, ttl_days) -> dict | None:
    """
    Return the most recent fresh amazon_search_cache row, or None.
    Fresh = fetched_at within ttl_days.
    """
    rows = _supabase_get(config, "serpapi_amazon_search_cache", {
        "search_phrase": f"eq.{search_phrase}",
        "country": f"eq.{country}",
        "pages": f"eq.{pages}",
        "fetched_at": f"gt.{_ttl_cutoff(ttl_days)}",
        "order": "fetched_at.desc",
        "limit": 1,
    })
    return rows[0] if rows else None


def cache_lookup_product(config, asin, country, ttl_days) -> dict | None:
    """
    Return the most recent fresh amazon_product_cache row for this ASIN, or None.
    """
    rows = _supabase_get(config, "serpapi_amazon_product_cache", {
        "asin": f"eq.{asin}",
        "country": f"eq.{country}",
        "fetched_at": f"gt.{_ttl_cutoff(ttl_days)}",
        "order": "fetched_at.desc",
        "limit": 1,
    })
    return rows[0] if rows else None


def store_search_result(config, search_phrase, country, pages, api_response) -> str:
    """
    Strip SerpAPI metadata, store search API response in amazon_search_cache.
    Returns the UUID of the inserted row.
    """
    cleaned = strip_serpapi_metadata(api_response)
    organic = cleaned.get("organic_results") or []
    row = {
        "search_phrase": search_phrase,
        "country": country,
        "pages": pages,
        "result_count": len(organic),
    }
    for col in SEARCH_SECTION_COLS:
        if col in cleaned:
            row[col] = json.dumps(cleaned[col])
    inserted = _supabase_post(config, "serpapi_amazon_search_cache", row)
    return inserted["id"]


def store_product_result(config, asin, country, api_response) -> str:
    """
    Strip SerpAPI metadata, store product API response in amazon_product_cache.
    Returns the UUID of the inserted row.
    """
    cleaned = strip_serpapi_metadata(api_response)
    row = {
        "asin": asin,
        "country": country,
    }
    for col in PRODUCT_SECTION_COLS:
        if col in cleaned:
            row[col] = json.dumps(cleaned[col])
    inserted = _supabase_post(config, "serpapi_amazon_product_cache", row)
    return inserted["id"]


def store_search_product_link(config, search_cache_id, product_cache_id, position):
    """
    Insert a row into amazon_search_product_link.
    ON CONFLICT is handled at the DB level (PRIMARY KEY constraint);
    if the link already exists the insert will error — callers should
    check for existing links before calling, or handle the exception.
    """
    _supabase_post(config, "serpapi_amazon_search_product_link", {
        "search_cache_id": search_cache_id,
        "product_cache_id": product_cache_id,
        "position": position,
    })


def main():
    parser = argparse.ArgumentParser(description="Amazon SerpAPI cache-first fetcher")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--search_phrase", help="Keyword to search on Amazon")
    group.add_argument("--asin", help="Amazon ASIN for direct product lookup")
    parser.add_argument("--country", default="amazon.com",
                        help="Amazon domain (default: amazon.com)")
    parser.add_argument("--pages", type=int, default=1,
                        help="Search result pages to fetch (default: 1)")
    parser.add_argument("--max_asins", type=int, default=10,
                        help="Max products to fetch details for (default: 10)")
    parser.add_argument("--ttl_days", type=int, default=30,
                        help="Cache freshness in days (default: 30)")
    parser.add_argument("--run_id", default=None,
                        help="Optional run UUID passed through to STATS line")
    args = parser.parse_args()

    if args.country not in VALID_DOMAINS:
        print(f"ERROR: Invalid country '{args.country}'. Must be one of: "
              f"{', '.join(sorted(VALID_DOMAINS))}")
        sys.exit(1)

    load_env()

    serpapi_key = os.environ.get("SERPAPI_API_KEY")
    if not serpapi_key:
        print("ERROR: SERPAPI_API_KEY not found in environment or .env")
        sys.exit(1)

    config = get_supabase_config()

    items_fetched = 0
    items_cached = 0
    items_stored = 0
    search_cache_id = None
    product_cache_ids = []

    if args.asin:
        # ── ASIN mode: product API only ──────────────────────────────────────
        prod_row = cache_lookup_product(config, args.asin, args.country, args.ttl_days)
        if prod_row:
            product_cache_ids.append(prod_row["id"])
            items_cached += 1
            print(json.dumps({
                "status": "cached",
                "asin": args.asin,
                "product_cache_id": prod_row["id"],
            }))
        else:
            try:
                response = fetch_product(serpapi_key, args.asin, country=args.country)
                items_fetched += 1
                product_cache_id = store_product_result(
                    config, args.asin, args.country, response
                )
                product_cache_ids.append(product_cache_id)
                items_stored += 1
                print(json.dumps({
                    "status": "stored",
                    "asin": args.asin,
                    "product_cache_id": product_cache_id,
                }))
            except Exception as e:
                print(f"ERROR: Failed to fetch/store ASIN {args.asin}: {e}")
                sys.exit(1)

    else:
        # ── Search term mode: search API + product API ───────────────────────
        normalized = clean_search_term(args.search_phrase)

        # Step 1: check search cache
        search_row = cache_lookup_search(
            config, normalized, args.country, args.pages, args.ttl_days
        )
        if search_row:
            search_cache_id = search_row["id"]
            organic = json.loads(search_row.get("organic_results") or "[]")
        else:
            # Fetch search API
            print(f"Fetching search results for: {args.search_phrase}")
            all_organic = []
            combined = {}
            for page_num in range(1, args.pages + 1):
                try:
                    page_data = search_amazon(
                        serpapi_key, args.search_phrase,
                        country=args.country, page=page_num
                    )
                    items_fetched += 1
                    all_organic.extend(page_data.get("organic_results", []))
                    if page_num == 1:
                        combined = page_data
                    else:
                        combined.setdefault("organic_results", []).extend(
                            page_data.get("organic_results", [])
                        )
                except Exception as e:
                    print(f"ERROR: Search API failed (page {page_num}): {e}")
                    sys.exit(1)

            combined["organic_results"] = all_organic
            search_cache_id = store_search_result(
                config, normalized, args.country, args.pages, combined
            )
            items_stored += 1
            organic = all_organic

        # Step 2: for each top ASIN, check product cache or fetch
        top_asins = extract_top_asins(organic, args.max_asins)
        print(f"Processing {len(top_asins)} ASINs...")

        for position, asin in top_asins:
            prod_row = cache_lookup_product(config, asin, args.country, args.ttl_days)
            if prod_row:
                product_cache_id = prod_row["id"]
                items_cached += 1
                print(json.dumps({
                    "status": "cached",
                    "asin": asin,
                    "product_cache_id": product_cache_id,
                }))
            else:
                try:
                    response = fetch_product(serpapi_key, asin, country=args.country)
                    items_fetched += 1
                    product_cache_id = store_product_result(
                        config, asin, args.country, response
                    )
                    items_stored += 1
                    print(json.dumps({
                        "status": "stored",
                        "asin": asin,
                        "product_cache_id": product_cache_id,
                    }))
                    time.sleep(0.3)
                except Exception as e:
                    print(f"WARNING: Failed to fetch/store ASIN {asin}: {e}")
                    continue

            product_cache_ids.append(product_cache_id)
            try:
                store_search_product_link(config, search_cache_id, product_cache_id, position)
            except Exception:
                pass  # link may already exist if ASIN was cached from a prior search

    product_ids_csv = ",".join(product_cache_ids)
    print(
        f"STATS:mode={'asin' if args.asin else 'search_term'},"
        f"search_cache_id={search_cache_id or 'null'},"
        f"product_cache_ids={product_ids_csv},"
        f"items_fetched={items_fetched},"
        f"items_cached={items_cached},"
        f"items_stored={items_stored},"
        f"run_id={args.run_id or 'null'}"
    )


if __name__ == "__main__":
    main()
