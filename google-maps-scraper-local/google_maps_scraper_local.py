#!/usr/bin/env python3
"""
google_maps_scraper_local.py
Scrapes Google Local Results via SerpApi and writes a deduplicated CSV.

Dependencies: pip install requests

Usage:
    python google_maps_scraper_local.py \
        --types "plumber,electrician" \
        --locations "Austin, TX,Dallas, TX" \
        --output "C:/Users/jeshj/Desktop/businesses.csv"

    Lat/lng is also accepted as a location:
        --locations "30.2672,-97.7431"

Reads SERPAPI_API_KEY from the .env file next to this script, then falls back
to a .env in the current working directory, then the environment.
"""

import argparse
import csv
import os
import re
import sys
import time

import requests

SERPAPI_URL = "https://serpapi.com/search"

# Detects "lat,lng" or "@lat,lng" with optional spaces around the comma
LAT_LNG_RE = re.compile(r'^@?(-?\d+\.?\d*),\s*(-?\d+\.?\d*)$')

US_STATES = {
    # Full names
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming",
    # Two-letter abbreviations
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
}

CSV_FIELDS = [
    "position", "place_id", "data_cid", "title", "phone", "address", "type", "rating",
    "reviews", "reviews_original", "price", "description", "hours", "website",
    "directions_url", "thumbnail", "place_id_search",
    "latitude", "longitude", "source_query", "source_location",
]


def load_env_file(path):
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
    # Check .env next to the script first, then fall back to cwd .env
    script_dir = os.path.dirname(os.path.abspath(__file__))
    load_env_file(os.path.join(script_dir, ".env"))
    load_env_file(os.path.join(os.getcwd(), ".env"))
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not key:
        print("ERROR: SERPAPI_API_KEY not found in environment or .env file.")
        print("Add it to: C:\\Users\\jeshj\\Desktop\\Coding\\_scripts\\google-maps-scraper-local\\.env")
        print("  SERPAPI_API_KEY=your_key_here")
        sys.exit(1)
    return key


def parse_lat_lng(location):
    """Returns (lat, lng) floats if the string is a coordinate pair, else None."""
    m = LAT_LNG_RE.match(location.strip())
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


def validate_locations(locations):
    """Returns a list of error messages for any state-only location strings."""
    errors = []
    for loc in locations:
        if loc.strip().lower() in US_STATES:
            errors.append(
                f"  '{loc}' — state-only searches are blocked. "
                f"Use 'City, State' instead (e.g. Houston, TX)"
            )
    return errors


def build_row(r, query, source_location):
    """Extract all CSV fields from a single local_results entry."""
    gps = r.get("gps_coordinates") or {}
    links = r.get("links") or {}
    return {
        "position": r.get("position", ""),
        "place_id": r.get("place_id", ""),
        "data_cid": r.get("data_cid", ""),
        "title": r.get("title", ""),
        "phone": r.get("phone", "") or links.get("phone", ""),
        "address": r.get("address", ""),
        "type": r.get("type", ""),
        "rating": r.get("rating", ""),
        "reviews": r.get("reviews", ""),
        "reviews_original": r.get("reviews_original", ""),
        "price": r.get("price", ""),
        "description": r.get("description", ""),
        "hours": r.get("hours", "") or r.get("open_state", ""),
        "website": links.get("website", ""),
        "directions_url": links.get("directions", ""),
        "thumbnail": r.get("thumbnail", ""),
        "place_id_search": r.get("place_id_search", ""),
        "latitude": gps.get("latitude", ""),
        "longitude": gps.get("longitude", ""),
        "source_query": query,
        "source_location": source_location,
    }


def _call_api(params, query, location):
    """Shared HTTP + error handling for both engines. Returns list of row dicts."""
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

    return [build_row(r, query, location) for r in data.get("local_results", [])]


def scrape_local(query, location, api_key):
    """engine=google_local — standard city/zip/address search."""
    params = {
        "engine": "google_local",
        "q": query,
        "location": location,
        "api_key": api_key,
        "hl": "en",
        "gl": "us",
    }
    return _call_api(params, query, location)


def scrape_maps(query, lat, lng, api_key, source_location):
    """engine=google_maps — GPS coordinate search via ll parameter."""
    ll = f"@{lat},{lng},14z"
    params = {
        "engine": "google_maps",
        "q": query,
        "ll": ll,
        "type": "search",
        "api_key": api_key,
        "hl": "en",
        "gl": "us",
    }
    return _call_api(params, query, source_location)


def scrape_one(query, location, api_key):
    """Route to the correct engine based on whether location is lat/lng or text."""
    coords = parse_lat_lng(location)
    if coords:
        lat, lng = coords
        return scrape_maps(query, lat, lng, api_key, location)
    return scrape_local(query, location, api_key)


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
    parser.add_argument("--location", action="append", dest="locations", required=True,
                        help="Location to search (repeat for multiple: --location 'Austin, TX' --location 'Dallas, TX')")
    parser.add_argument("--output", required=True, help="Output CSV file path")
    args = parser.parse_args()

    api_key = get_api_key()

    types = [t.strip() for t in args.types.split(",") if t.strip()]
    locations = [loc.strip() for loc in args.locations if loc.strip()]

    if not types:
        print("ERROR: --types cannot be empty")
        sys.exit(1)
    if not locations:
        print("ERROR: --locations cannot be empty")
        sys.exit(1)

    errors = validate_locations(locations)
    if errors:
        print("ERROR: Invalid location(s) — state-only searches are not allowed:")
        for e in errors:
            print(e)
        sys.exit(1)

    total_calls = len(types) * len(locations)
    print(f"Running {total_calls} API calls ({len(types)} type(s) x {len(locations)} location(s))...")

    all_rows = []
    failed_calls = 0

    for btype in types:
        for loc in locations:
            engine = "google_maps" if parse_lat_lng(loc) else "google_local"
            print(f"  Scraping '{btype}' in '{loc}' [{engine}]...", end=" ", flush=True)
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

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(deduped)

    print(f"STATS:raw={raw_count},deduped={deduped_count},failed={failed_calls},output={output_path}")


if __name__ == "__main__":
    main()
