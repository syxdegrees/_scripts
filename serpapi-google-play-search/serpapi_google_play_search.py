#!/usr/bin/env python3
"""
Google Play Store SerpAPI cache-first fetcher.

Checks Supabase for fresh data before calling the API.
Stores raw API sections as JSONB columns in intermediary tables.
Emits JSON lines + STATS to stdout for the calling skill.

Usage:
  python serpapi_google_play_search.py --search_phrase "fitness apps" --store_type apps
  python serpapi_google_play_search.py --product_id "com.example.app" --store_type apps --with_reviews
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

SEARCH_ENGINES = {
    "apps":   "google_play",
    "games":  "google_play_games",
    "movies": "google_play_movies",
    "books":  "google_play_books",
}

_SERPAPI_META_KEYS = {"search_metadata", "search_parameters", "serpapi_pagination"}


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


def search_google_play(api_key, phrase, store_type, gl="us", hl="en"):
    engine = SEARCH_ENGINES.get(store_type)
    if not engine:
        print(f"ERROR: store_type '{store_type}' has no search engine (use: {list(SEARCH_ENGINES)})")
        sys.exit(1)
    return serpapi_get(api_key, {
        "engine": engine,
        "q": phrase,
        "gl": gl,
        "hl": hl,
    })


def fetch_product(api_key, product_id, store_type, gl="us", hl="en", with_reviews=False):
    params = {
        "engine": "google_play_product",
        "product_id": product_id,
        "store": store_type,
        "gl": gl,
        "hl": hl,
    }
    if with_reviews:
        params["all_reviews"] = "true"
    return serpapi_get(api_key, params)


def get_supabase_config():
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


def _ttl_cutoff(ttl_days: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    return cutoff.isoformat()


def strip_serpapi_metadata(response: dict) -> dict:
    return {k: v for k, v in response.items() if k not in _SERPAPI_META_KEYS}


def clean_search_term(term: str) -> str:
    term = term.lower().strip()
    term = re.sub(r"\s+", "-", term)
    term = re.sub(r"[^a-z0-9-]", "", term)
    term = re.sub(r"-+", "-", term)
    return term.strip("-")


def extract_top_items(organic_results: list, max_items: int) -> list:
    """
    Flatten sections -> items and return list of (position, product_id) tuples.
    organic_results is [{title, items: [{product_id, ...}]}].
    product_id is a string — standard truthiness check is fine.
    """
    result = []
    for section in organic_results:
        for item in section.get("items", []):
            product_id = item.get("product_id")
            if product_id:
                result.append((len(result), product_id))
            if len(result) == max_items:
                return result
    return result


def cache_lookup_search(config, search_phrase, store_type, gl, hl, ttl_days) -> dict | None:
    rows = _supabase_get(config, "serpapi_google_play_search", {
        "search_phrase": f"eq.{search_phrase}",
        "store_type": f"eq.{store_type}",
        "gl": f"eq.{gl}",
        "hl": f"eq.{hl}",
        "fetched_at": f"gt.{_ttl_cutoff(ttl_days)}",
        "order": "fetched_at.desc",
        "limit": 1,
    })
    return rows[0] if rows else None


def cache_lookup_product(config, product_id, store_type, gl, hl, with_reviews, ttl_days) -> dict | None:
    params = {
        "product_id": f"eq.{product_id}",
        "store_type": f"eq.{store_type}",
        "gl": f"eq.{gl}",
        "hl": f"eq.{hl}",
        "fetched_at": f"gt.{_ttl_cutoff(ttl_days)}",
        "order": "fetched_at.desc",
        "limit": 1,
    }
    if with_reviews:
        params["with_reviews"] = "eq.true"
    rows = _supabase_get(config, "serpapi_google_play_product", params)
    return rows[0] if rows else None


def store_search_result(config, search_phrase, store_type, gl, hl, api_response) -> str:
    cleaned = strip_serpapi_metadata(api_response)
    row = {
        "search_phrase": search_phrase,
        "store_type": store_type,
        "gl": gl,
        "hl": hl,
    }
    if "organic_results" in cleaned:
        row["organic_results"] = json.dumps(cleaned["organic_results"])
    inserted = _supabase_post(config, "serpapi_google_play_search", row)
    return inserted["id"]


def store_product_result(config, product_id, store_type, gl, hl, with_reviews, api_response) -> str:
    cleaned = strip_serpapi_metadata(api_response)
    row = {
        "product_id": product_id,
        "store_type": store_type,
        "gl": gl,
        "hl": hl,
        "with_reviews": with_reviews,
    }
    if "product_results" in cleaned:
        row["product_results"] = json.dumps(cleaned["product_results"])
    if with_reviews and "reviews" in cleaned:
        row["reviews"] = json.dumps(cleaned["reviews"])
    inserted = _supabase_post(config, "serpapi_google_play_product", row)
    return inserted["id"]


def store_search_product_link(config, search_cache_id, product_cache_id, position):
    _supabase_post(config, "serpapi_google_play_search_product_link", {
        "search_cache_id": search_cache_id,
        "product_cache_id": product_cache_id,
        "position": position,
    })


def main():
    parser = argparse.ArgumentParser(description="Google Play Store SerpAPI cache-first fetcher")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--search_phrase", help="Term to search on Google Play")
    group.add_argument("--product_id", help="Google Play product ID for direct lookup")
    parser.add_argument(
        "--store_type", required=True,
        choices=["apps", "games", "movies", "tv", "books", "audiobooks"],
        help="Google Play store type",
    )
    parser.add_argument("--gl", default="us", help="Country code (default: us)")
    parser.add_argument("--hl", default="en", help="Language code (default: en)")
    parser.add_argument("--max_items", type=int, default=10,
                        help="Max products to fetch details for (default: 10, search mode only)")
    parser.add_argument("--with_reviews", action="store_true",
                        help="Fetch reviews inline via all_reviews=true (product_id mode only)")
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
    product_cache_ids = []

    if args.product_id:
        # ── product_id mode ───────────────────────────────────────────────────
        prod_row = cache_lookup_product(
            config, args.product_id, args.store_type, args.gl, args.hl,
            args.with_reviews, args.ttl_days
        )
        if prod_row:
            product_cache_id = prod_row["id"]
            items_cached += 1
            print(json.dumps({
                "status": "cached",
                "product_id": args.product_id,
                "product_cache_id": product_cache_id,
            }))
        else:
            try:
                response = fetch_product(
                    serpapi_key, args.product_id, args.store_type,
                    gl=args.gl, hl=args.hl, with_reviews=args.with_reviews
                )
                items_fetched += 1
                product_cache_id = store_product_result(
                    config, args.product_id, args.store_type, args.gl, args.hl,
                    args.with_reviews, response
                )
                items_stored += 1
                print(json.dumps({
                    "status": "stored",
                    "product_id": args.product_id,
                    "product_cache_id": product_cache_id,
                }))
            except Exception as e:
                print(f"ERROR: Failed to fetch/store product {args.product_id}: {e}")
                sys.exit(1)

        print(
            f"STATS:mode=product_id,"
            f"product_cache_id={product_cache_id or 'null'},"
            f"items_fetched={items_fetched},"
            f"items_cached={items_cached},"
            f"items_stored={items_stored},"
            f"run_id={args.run_id or 'null'}"
        )

    else:
        # ── search_phrase mode ────────────────────────────────────────────────
        normalized = clean_search_term(args.search_phrase)

        search_row = cache_lookup_search(
            config, normalized, args.store_type, args.gl, args.hl, args.ttl_days
        )
        if search_row:
            search_cache_id = search_row["id"]
            organic = json.loads(search_row.get("organic_results") or "[]")
        else:
            print(f"Fetching search results for: {args.search_phrase} ({args.store_type})")
            try:
                api_response = search_google_play(
                    serpapi_key, args.search_phrase, args.store_type,
                    gl=args.gl, hl=args.hl
                )
                items_fetched += 1
                search_cache_id = store_search_result(
                    config, normalized, args.store_type, args.gl, args.hl, api_response
                )
                items_stored += 1
                organic = api_response.get("organic_results", [])
            except Exception as e:
                print(f"ERROR: Search API failed: {e}")
                sys.exit(1)

        top_items = extract_top_items(organic, args.max_items)
        print(f"Processing {len(top_items)} items...")

        for position, product_id in top_items:
            prod_row = cache_lookup_product(
                config, product_id, args.store_type, args.gl, args.hl, False, args.ttl_days
            )
            if prod_row:
                product_cache_id = prod_row["id"]
                items_cached += 1
                print(json.dumps({
                    "status": "cached",
                    "product_id": product_id,
                    "product_cache_id": product_cache_id,
                }))
            else:
                try:
                    response = fetch_product(
                        serpapi_key, product_id, args.store_type,
                        gl=args.gl, hl=args.hl, with_reviews=False
                    )
                    items_fetched += 1
                    product_cache_id = store_product_result(
                        config, product_id, args.store_type, args.gl, args.hl, False, response
                    )
                    items_stored += 1
                    print(json.dumps({
                        "status": "stored",
                        "product_id": product_id,
                        "product_cache_id": product_cache_id,
                    }))
                    time.sleep(0.3)
                except Exception as e:
                    print(f"WARNING: Failed to fetch/store {product_id}: {e}")
                    continue

            product_cache_ids.append(product_cache_id)
            try:
                store_search_product_link(config, search_cache_id, product_cache_id, position)
            except Exception:
                pass  # link may already exist if product was cached from a prior search

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
