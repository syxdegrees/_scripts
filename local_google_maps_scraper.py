#!/usr/bin/env python3
"""
local_google_maps_scraper.py
Scrapes Google Local Results via SerpApi and writes a deduplicated CSV.

Dependencies: pip install requests

Usage:
    python local_google_maps_scraper.py \
        --types "plumber,electrician" \
        --locations "Austin, TX,Dallas, TX" \
        --output "C:/Users/jeshj/Desktop/businesses.csv"

Reads SERPAPI_API_KEY from environment or a .env file in the current directory.
"""

import argparse
import csv
import os
import sys
import time

import requests

SERPAPI_URL = "https://serpapi.com/search"

CSV_FIELDS = [
    "place_id", "title", "phone", "address", "type", "rating",
    "reviews", "price", "description", "hours", "website",
    "directions_url", "latitude", "longitude",
    "source_query", "source_location",
]


def load_env_file(path=".env"):
    """Load key=value pairs from a .env file into os.environ (does not overwrite existing vars)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def get_api_key():
    load_env_file()
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not key:
        print("ERROR: SERPAPI_API_KEY not found in environment or .env file.")
        print("Add it to your .env file:")
        print("  SERPAPI_API_KEY=your_key_here")
        sys.exit(1)
    return key


def scrape_one(query, location, api_key):
    """Call SerpApi for one query+location pair. Returns list of row dicts."""
    params = {
        "engine": "google_local",
        "q": query,
        "location": location,
        "api_key": api_key,
        "hl": "en",
        "gl": "us",
    }
    try:
        resp = requests.get(SERPAPI_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        print(f"  WARNING: Network/HTTP error for '{query}' in '{location}': {e}")
        return []

    if "error" in data:
        err = data["error"]
        if "api" in err.lower() and "key" in err.lower():
            print(f"ERROR: SerpApi authentication failed: {err}")
            sys.exit(1)
        print(f"  WARNING: SerpApi error for '{query}' in '{location}': {err}")
        return []

    rows = []
    for r in data.get("local_results", []):
        gps = r.get("gps_coordinates") or {}
        links = r.get("links") or {}
        rows.append({
            "place_id": r.get("place_id", ""),
            "title": r.get("title", ""),
            "phone": r.get("phone", ""),
            "address": r.get("address", ""),
            "type": r.get("type", ""),
            "rating": r.get("rating", ""),
            "reviews": r.get("reviews", ""),
            "price": r.get("price", ""),
            "description": r.get("description", ""),
            "hours": r.get("hours", ""),
            "website": links.get("website", ""),
            "directions_url": links.get("directions", ""),
            "latitude": gps.get("latitude", ""),
            "longitude": gps.get("longitude", ""),
            "source_query": query,
            "source_location": location,
        })
    return rows


def deduplicate(rows):
    """Keep the first occurrence of each place_id. Rows with no place_id are always kept."""
    seen = set()
    deduped = []
    for row in rows:
        pid = row.get("place_id", "")
        if pid:
            if pid not in seen:
                seen.add(pid)
                deduped.append(row)
        else:
            deduped.append(row)
    return deduped


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Google Local businesses via SerpApi"
    )
    parser.add_argument("--types", required=True, help="Comma-separated business types")
    parser.add_argument("--locations", required=True, help="Comma-separated locations")
    parser.add_argument("--output", required=True, help="Output CSV file path")
    args = parser.parse_args()

    api_key = get_api_key()

    types = [t.strip() for t in args.types.split(",") if t.strip()]
    locations = [loc.strip() for loc in args.locations.split(",") if loc.strip()]

    if not types:
        print("ERROR: --types cannot be empty")
        sys.exit(1)
    if not locations:
        print("ERROR: --locations cannot be empty")
        sys.exit(1)

    total_calls = len(types) * len(locations)
    print(f"Running {total_calls} API calls ({len(types)} type(s) x {len(locations)} location(s))...")

    all_rows = []
    failed_calls = 0

    for btype in types:
        for loc in locations:
            print(f"  Scraping '{btype}' in '{loc}'...", end=" ", flush=True)
            rows = scrape_one(btype, loc, api_key)
            if rows:
                print(f"{len(rows)} results")
                all_rows.extend(rows)
            else:
                print("0 results (see WARNING above if any)")
                failed_calls += 1
            time.sleep(0.5)

    if not all_rows and failed_calls == total_calls:
        print("ERROR: All API calls failed. Check your SERPAPI_API_KEY and network.")
        sys.exit(1)

    raw_count = len(all_rows)
    deduped = deduplicate(all_rows)
    deduped_count = len(deduped)

    output_path = os.path.abspath(args.output)
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(deduped)

    print(f"STATS:raw={raw_count},deduped={deduped_count},failed={failed_calls},output={output_path}")


if __name__ == "__main__":
    main()
