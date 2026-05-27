#!/usr/bin/env python3
"""
Apple App Store SerpAPI cache-first fetcher.

Checks Supabase for fresh data before calling the API.
Stores raw API sections as JSONB columns in intermediary tables.
Emits JSON lines + STATS to stdout for the calling skill.

Usage:
  python serpapi_apple_app_store_search.py --search_phrase "fitness tracker" --max_items 10
  python serpapi_apple_app_store_search.py --app_id 1234567890
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

# Columns in serpapi_apple_app_store_search_cache that hold API section data (nullable JSONB).
SEARCH_SECTION_COLS = {
    "search_information",
    "organic_results",
}

# JSONB columns in serpapi_apple_app_store_reviews_cache.
REVIEWS_JSONB_COLS = {
    "search_information",
    "reviews",
}

# No scalar columns for Apple reviews (no overall_rating / total_count equivalents).
REVIEWS_SCALAR_COLS = set()

# No scalar field remapping needed for Apple reviews.
_REVIEWS_SCALAR_MAP = {}


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


def search_apple_app_store(api_key, phrase, country="us", page=1):
    return serpapi_get(api_key, {
        "engine": "apple_app_store",
        "term": phrase,
        "country": country,
        "num": 10,
        "page": page - 1,  # Apple App Store API uses 0-indexed pages
    })


def fetch_product(api_key, app_id, country="us"):
    return serpapi_get(api_key, {
        "engine": "apple_product",
        "product_id": app_id,
        "country": country,
    })


def fetch_reviews(api_key, app_id, country="us", page=1):
    return serpapi_get(api_key, {
        "engine": "apple_reviews",
        "product_id": app_id,
        "country": country,
        "page": page,
    })


def fetch_reviews_paginated(api_key, app_id, country, review_pages):
    """Fetch review_pages pages and merge reviews arrays into one combined response."""
    combined = {}
    all_reviews = []
    for page_num in range(1, review_pages + 1):
        page_data = fetch_reviews(api_key, app_id, country=country, page=page_num)
        if page_num == 1:
            combined = page_data
        all_reviews.extend(page_data.get("reviews", []))
        if page_num < review_pages:
            time.sleep(0.3)
    combined["reviews"] = all_reviews
    return combined


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


def _supabase_patch(config, table, row_id, updates):
    """PATCH (partial update) a row in Supabase REST API by ID."""
    try:
        import requests
    except ImportError:
        print("ERROR: requests library not installed. Run: pip install requests")
        sys.exit(1)
    url = f"{config['url']}/rest/v1/{table}"
    headers = {**_supabase_headers(config), "Prefer": "return=representation"}
    resp = requests.patch(url, headers=headers, params={"id": f"eq.{row_id}"}, json=updates, timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else {}


_SERPAPI_META_KEYS = {"search_metadata", "search_parameters", "serpapi_pagination"}


def strip_serpapi_metadata(response: dict) -> dict:
    """Return a copy of response with SerpAPI housekeeping keys removed."""
    return {k: v for k, v in response.items() if k not in _SERPAPI_META_KEYS}


def extract_top_items(organic_results: list, max_items: int) -> list:
    """
    Return list of (position, app_id) tuples from organic_results.
    position = original index in organic_results (0-based).
    Skips items without an 'id' key. Returns at most max_items items.
    """
    result = []
    for i, item in enumerate(organic_results):
        app_id = item.get("id")
        if app_id is not None:
            result.append((i, str(app_id)))
        if len(result) == max_items:
            break
    return result


def _ttl_cutoff(ttl_days: int) -> str:
    """ISO 8601 timestamp for the oldest acceptable fetched_at."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    return cutoff.isoformat()


def cache_lookup_search(config, search_phrase, country, ttl_days) -> dict | None:
    """Return the most recent fresh search cache row, or None. No pages filter — top-up handles gaps."""
    rows = _supabase_get(config, "serpapi_apple_app_store_search_cache", {
        "search_phrase": f"eq.{search_phrase}",
        "country": f"eq.{country}",
        "fetched_at": f"gt.{_ttl_cutoff(ttl_days)}",
        "order": "fetched_at.desc",
        "limit": 1,
    })
    return rows[0] if rows else None


def cache_lookup_product(config, app_id, country, ttl_days) -> dict | None:
    """Return the most recent fresh product cache row for this app, or None."""
    rows = _supabase_get(config, "serpapi_apple_app_store_product_cache", {
        "app_id": f"eq.{app_id}",
        "country": f"eq.{country}",
        "fetched_at": f"gt.{_ttl_cutoff(ttl_days)}",
        "order": "fetched_at.desc",
        "limit": 1,
    })
    return rows[0] if rows else None


def cache_lookup_reviews(config, app_id, country, review_pages, ttl_days) -> dict | None:
    """Return the most recent fresh reviews cache row for this app, or None."""
    rows = _supabase_get(config, "serpapi_apple_app_store_reviews_cache", {
        "app_id": f"eq.{app_id}",
        "country": f"eq.{country}",
        "review_pages": f"eq.{review_pages}",
        "fetched_at": f"gt.{_ttl_cutoff(ttl_days)}",
        "order": "fetched_at.desc",
        "limit": 1,
    })
    return rows[0] if rows else None


def store_search_result(config, search_phrase, country, pages, api_response) -> str:
    """Strip SerpAPI metadata, store search response. Returns the UUID of the inserted row."""
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
    inserted = _supabase_post(config, "serpapi_apple_app_store_search_cache", row)
    return inserted["id"]


def store_product_result(config, app_id, country, api_response) -> str:
    """Strip SerpAPI metadata, store entire product response as one blob. Returns UUID."""
    cleaned = strip_serpapi_metadata(api_response)
    row = {
        "app_id": app_id,
        "country": country,
        "product_results": json.dumps(cleaned),
    }
    inserted = _supabase_post(config, "serpapi_apple_app_store_product_cache", row)
    return inserted["id"]


def store_reviews_result(config, app_id, country, review_pages, api_response) -> str:
    """Strip SerpAPI metadata, store reviews response. Returns the UUID of the inserted row."""
    cleaned = strip_serpapi_metadata(api_response)
    row = {
        "app_id": app_id,
        "country": country,
        "review_pages": review_pages,
    }
    for col in REVIEWS_JSONB_COLS:
        if col in cleaned:
            row[col] = json.dumps(cleaned[col])
    inserted = _supabase_post(config, "serpapi_apple_app_store_reviews_cache", row)
    return inserted["id"]


def store_search_product_link(config, search_cache_id, product_cache_id, position):
    """Insert a row into serpapi_apple_app_store_search_product_link."""
    _supabase_post(config, "serpapi_apple_app_store_search_product_link", {
        "search_cache_id": search_cache_id,
        "product_cache_id": product_cache_id,
        "position": position,
    })


def main():
    parser = argparse.ArgumentParser(description="Apple App Store SerpAPI cache-first fetcher")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--search_phrase", help="Term to search on Apple App Store")
    group.add_argument("--app_id", help="Apple App Store app ID for direct product/reviews lookup")
    parser.add_argument("--country", default="us",
                        help="Country code (default: us)")
    parser.add_argument("--pages", type=int, default=1,
                        help="Search result pages to fetch (default: 1)")
    parser.add_argument("--max_items", type=int, default=10,
                        help="Max apps to fetch details for (default: 10)")
    parser.add_argument("--review_pages", type=int, default=1,
                        help="Review pages to fetch per app (default: 1)")
    parser.add_argument("--ttl_days", type=int, default=30,
                        help="Cache freshness in days (default: 30)")
    parser.add_argument("--run_id", default=None,
                        help="Optional run UUID passed through to STATS line")
    args = parser.parse_args()

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
    product_cache_id = None
    reviews_cache_id = None
    product_cache_ids = []

    if args.app_id:
        # ── app_id mode: product API + reviews API ────────────────────────────
        app_id = str(args.app_id)

        # Product
        prod_row = cache_lookup_product(config, app_id, args.country, args.ttl_days)
        if prod_row:
            product_cache_id = prod_row["id"]
            items_cached += 1
            print(json.dumps({
                "status": "cached",
                "app_id": app_id,
                "type": "product",
                "product_cache_id": product_cache_id,
            }))
        else:
            try:
                response = fetch_product(serpapi_key, app_id, country=args.country)
                items_fetched += 1
                product_cache_id = store_product_result(
                    config, app_id, args.country, response
                )
                items_stored += 1
                print(json.dumps({
                    "status": "stored",
                    "app_id": app_id,
                    "type": "product",
                    "product_cache_id": product_cache_id,
                }))
            except Exception as e:
                print(f"ERROR: Failed to fetch/store product for {app_id}: {e}")
                sys.exit(1)

        # Reviews
        rev_row = cache_lookup_reviews(
            config, app_id, args.country, args.review_pages, args.ttl_days
        )
        if rev_row:
            reviews_cache_id = rev_row["id"]
            items_cached += 1
            print(json.dumps({
                "status": "cached",
                "app_id": app_id,
                "type": "reviews",
                "reviews_cache_id": reviews_cache_id,
            }))
        else:
            try:
                response = fetch_reviews_paginated(
                    serpapi_key, app_id, args.country, args.review_pages
                )
                items_fetched += args.review_pages
                reviews_cache_id = store_reviews_result(
                    config, app_id, args.country, args.review_pages, response
                )
                items_stored += 1
                print(json.dumps({
                    "status": "stored",
                    "app_id": app_id,
                    "type": "reviews",
                    "reviews_cache_id": reviews_cache_id,
                }))
            except Exception as e:
                print(f"ERROR: Failed to fetch/store reviews for {app_id}: {e}")
                sys.exit(1)

    else:
        # ── Search term mode: search API + product API ────────────────────────
        normalized = clean_search_term(args.search_phrase)

        # Step 1: check search cache
        search_row = cache_lookup_search(
            config, normalized, args.country, args.ttl_days
        )
        if search_row:
            search_cache_id = search_row["id"]
            organic = json.loads(search_row.get("organic_results") or "[]")
            cached_pages = search_row.get("pages", 1)
        else:
            print(f"Fetching search results for: {args.search_phrase}")
            all_organic = []
            combined = {}
            for page_num in range(1, args.pages + 1):
                try:
                    page_data = search_apple_app_store(
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
            cached_pages = args.pages

        # Top-up: fetch additional pages if cached results fall short of max_items
        if len(organic) < args.max_items:
            seen_ids = {str(item.get("id")) for item in organic if item.get("id") is not None}
            next_page = cached_pages + 1
            extra_pages = 0
            while len(organic) < args.max_items and extra_pages < 10:
                try:
                    page_data = search_apple_app_store(
                        serpapi_key, args.search_phrase,
                        country=args.country, page=next_page
                    )
                    items_fetched += 1
                    new_results = page_data.get("organic_results", [])
                    if not new_results:
                        break
                    added = 0
                    for item in new_results:
                        item_id = str(item.get("id")) if item.get("id") is not None else None
                        if item_id and item_id not in seen_ids:
                            organic.append(item)
                            seen_ids.add(item_id)
                            added += 1
                    if added == 0:
                        break
                    extra_pages += 1
                    next_page += 1
                except Exception as e:
                    print(f"WARNING: Top-up page {next_page} failed: {e}")
                    break
            if extra_pages > 0:
                _supabase_patch(config, "serpapi_apple_app_store_search_cache", search_cache_id, {
                    "organic_results": json.dumps(organic),
                    "result_count": len(organic),
                    "pages": cached_pages + extra_pages,
                })

        # Step 2: for each top app, check product cache or fetch
        top_items = extract_top_items(organic, args.max_items)
        print(f"Processing {len(top_items)} items...")

        for position, app_id in top_items:
            prod_row = cache_lookup_product(config, app_id, args.country, args.ttl_days)
            if prod_row:
                product_cache_id = prod_row["id"]
                items_cached += 1
                print(json.dumps({
                    "status": "cached",
                    "app_id": app_id,
                    "product_cache_id": product_cache_id,
                }))
            else:
                try:
                    response = fetch_product(serpapi_key, app_id, country=args.country)
                    items_fetched += 1
                    product_cache_id = store_product_result(
                        config, app_id, args.country, response
                    )
                    items_stored += 1
                    print(json.dumps({
                        "status": "stored",
                        "app_id": app_id,
                        "product_cache_id": product_cache_id,
                    }))
                    time.sleep(0.3)
                except Exception as e:
                    print(f"WARNING: Failed to fetch/store app {app_id}: {e}")
                    continue

            product_cache_ids.append(product_cache_id)
            try:
                store_search_product_link(
                    config, search_cache_id, product_cache_id, position
                )
            except Exception:
                pass  # link may already exist if app was cached from a prior search

    if args.app_id:
        print(
            f"STATS:mode=app_id,"
            f"product_cache_id={product_cache_id or 'null'},"
            f"reviews_cache_id={reviews_cache_id or 'null'},"
            f"items_fetched={items_fetched},"
            f"items_cached={items_cached},"
            f"items_stored={items_stored},"
            f"run_id={args.run_id or 'null'}"
        )
    else:
        product_ids_csv = ",".join(product_cache_ids)
        print(
            f"STATS:mode=search_term,"
            f"search_cache_id={search_cache_id or 'null'},"
            f"product_cache_ids={product_ids_csv},"
            f"items_fetched={items_fetched},"
            f"items_cached={items_cached},"
            f"items_stored={items_stored},"
            f"run_id={args.run_id or 'null'}"
        )


if __name__ == "__main__":
    main()
