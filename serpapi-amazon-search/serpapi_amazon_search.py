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

VALID_DOMAINS = {
    "amazon.com", "amazon.co.uk", "amazon.ca", "amazon.de",
    "amazon.fr", "amazon.es", "amazon.it", "amazon.co.jp",
    "amazon.in", "amazon.com.au", "amazon.com.mx",
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


def extract_asins_from_search(search_data):
    asins = []
    for item in search_data.get("organic_results", []):
        asin = item.get("asin")
        if asin and asin not in asins:
            asins.append(asin)
    return asins


# ── Mapping helpers ───────────────────────────────────────────────────────────

def load_mapping(path):
    """Load and validate a mapping JSON file. Returns list of table mapping dicts."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Mapping file not found: {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Mapping file is not valid JSON: {e}")
        sys.exit(1)

    if isinstance(data, dict):
        data = [data]

    for i, entry in enumerate(data):
        if "table" not in entry:
            print(f"ERROR: Mapping entry {i} missing required field 'table'")
            sys.exit(1)
        if "fields" not in entry or not isinstance(entry["fields"], list):
            print(f"ERROR: Mapping entry {i} missing required field 'fields' (must be a list)")
            sys.exit(1)
        for j, field in enumerate(entry["fields"]):
            for required in ("source_section", "source_field", "dest_column"):
                if required not in field:
                    print(f"ERROR: Mapping entry {i}, field {j} missing '{required}'")
                    sys.exit(1)
            phase = field.get("phase")
            if phase is not None and phase not in ("search", "product"):
                print(f"ERROR: Mapping entry {i}, field {j} has invalid phase '{phase}' "
                      f"(must be 'search' or 'product')")
                sys.exit(1)

    return data


def extract_field(obj, field_path):
    """Dot-notation accessor for nested dicts. Returns None if any key is missing."""
    if not isinstance(obj, dict):
        return None
    current = obj
    for part in field_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def build_mapped_search_row(item, table_mapping):
    """
    Extract mapped fields from a single search result item (e.g., one organic_results entry).
    source_section is ignored — all fields are extracted directly from item.
    Returns {dest_column: value} dict.
    """
    row = {}
    for field in table_mapping["fields"]:
        row[field["dest_column"]] = extract_field(item, field["source_field"])
    return row


def build_mapped_product_row(product_response, table_mapping):
    """
    Extract mapped fields from a full product API response dict (keyed by section name).
    Array sections are stored as-is (JSON). Nested dict fields use dot notation.
    Returns {dest_column: value} dict.
    """
    row = {}
    for field in table_mapping["fields"]:
        section_data = product_response.get(field["source_section"])
        dest_col = field["dest_column"]
        if section_data is None:
            row[dest_col] = None
        elif isinstance(section_data, list):
            row[dest_col] = section_data
        elif isinstance(section_data, dict):
            row[dest_col] = extract_field(section_data, field["source_field"])
        else:
            row[dest_col] = section_data
    return row


def build_row_from_mapping(search_item, product_response, table_mapping):
    """
    Build a single merged row from both search and product API data (two-phase, Branch B1).
    phase:'search' fields come from search_item; phase:'product' fields from product_response.
    Returns {dest_column: value} dict.
    """
    row = {}
    for field in table_mapping["fields"]:
        phase = field.get("phase")
        dest_col = field["dest_column"]

        if phase == "search":
            row[dest_col] = extract_field(search_item, field["source_field"])
        else:
            section_data = product_response.get(field["source_section"])
            if section_data is None:
                row[dest_col] = None
            elif isinstance(section_data, list):
                row[dest_col] = section_data
            elif isinstance(section_data, dict):
                row[dest_col] = extract_field(section_data, field["source_field"])
            else:
                row[dest_col] = section_data
    return row


def write_csv(rows, path):
    import csv
    if not rows:
        print("WARNING: No rows to write to CSV.")
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(dict.fromkeys(k for row in rows for k in row))
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV written: {path} ({len(rows)} rows)")


def write_csv_by_table(csv_rows_by_table, output_folder, phrase_label):
    """Write one dated CSV per table entry when --csv_output is a folder (multiple destinations)."""
    import csv
    import re
    from datetime import date
    folder = Path(output_folder)
    folder.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y-%m-%d")
    safe_label = re.sub(r"[^a-z0-9-]", "", re.sub(r"\s+", "-", phrase_label.lower())).strip("-")
    for table_name, rows in csv_rows_by_table.items():
        if not rows:
            continue
        file_path = folder / f"{today}_{safe_label}_{table_name}.csv"
        fieldnames = list(dict.fromkeys(k for row in rows for k in row))
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        print(f"CSV written: {file_path} ({len(rows)} rows)")


def main():
    parser = argparse.ArgumentParser(description="Amazon SerpAPI extractor")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--search_phrase", help="Keyword to search on Amazon")
    group.add_argument("--asin", help="Amazon ASIN for direct product lookup")
    parser.add_argument("--sections", required=True,
                        help="Comma-separated section names to fetch")
    parser.add_argument("--supabase_url", default=None,
                        help="Supabase project URL")
    parser.add_argument("--supabase_key", default=None,
                        help="Supabase service role key")
    parser.add_argument("--csv_output", default=None,
                        help="Local CSV file path for output (no Supabase required)")
    parser.add_argument("--run_id", default=None,
                        help="Optional run UUID for linking results")
    parser.add_argument("--max_asins", type=int, default=10,
                        help="Max ASINs to fetch in two-stage mode (default: 10)")
    parser.add_argument("--country", default="amazon.com",
                        help="Amazon domain (e.g. amazon.com, amazon.co.uk)")
    parser.add_argument("--pages", type=int, default=1,
                        help="Number of search result pages to fetch (default: 1)")
    parser.add_argument("--mapping", required=True,
                        help="Path to mapping JSON file")
    args = parser.parse_args()

    if args.country not in VALID_DOMAINS:
        print(f"ERROR: Invalid country '{args.country}'. Must be one of: {', '.join(sorted(VALID_DOMAINS))}")
        sys.exit(1)

    has_csv = bool(args.csv_output)
    has_supabase = bool(args.supabase_url and args.supabase_key)
    if not has_supabase and not has_csv:
        print("ERROR: --mapping requires --supabase_url and --supabase_key, or --csv_output.")
        sys.exit(1)

    load_env()

    mapping = load_mapping(args.mapping)

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
    csv_rows = []
    # Multi-table CSV mode: mapping has more than 1 table entry.
    # csv_output is treated as a folder; one file is written per table.
    csv_output_is_dir = bool(args.csv_output and mapping and len(mapping) > 1)
    csv_rows_by_table: dict = {}

    if args.asin:
        # --- ASIN mode ---
        phrase_label = f"ASIN:{args.asin}"
        print(f"Fetching product page for ASIN {args.asin}...")
        try:
            product_data = fetch_product(serpapi_key, args.asin, country=args.country)

            for table_mapping in mapping:
                row = build_mapped_product_row(product_data, table_mapping)
                if args.run_id:
                    row["run_id"] = args.run_id
                if has_supabase:
                    supabase_insert(args.supabase_url, args.supabase_key,
                                    table_mapping["table"], row)
                if has_csv:
                    if csv_output_is_dir:
                        csv_rows_by_table.setdefault(table_mapping["table"], []).append(row)
                    else:
                        csv_rows.append(row)
            rows_saved += 1

        except Exception as e:
            print(f"WARNING: Failed to fetch/save ASIN {args.asin}: {e}")
            failed += 1

        if has_csv:
            if csv_output_is_dir:
                write_csv_by_table(csv_rows_by_table, args.csv_output, phrase_label)
            else:
                write_csv(csv_rows, args.csv_output)
        print(f"STATS:mode=asin,search_phrase={phrase_label},"
              f"products=1,rows_saved={rows_saved},failed={failed}")

    else:
        # --- Search Term mode ---
        phrase_label = args.search_phrase
        print(f"Searching Amazon for: {phrase_label}")

        all_search_data = {}
        for page_num in range(1, args.pages + 1):
            try:
                page_data = search_amazon(serpapi_key, args.search_phrase,
                                          country=args.country, page=page_num)
            except Exception as e:
                print(f"ERROR: Amazon search failed (page {page_num}): {e}")
                sys.exit(1)
            for section in SEARCH_SECTIONS:
                if section in page_data:
                    val = page_data[section]
                    if isinstance(val, list):
                        all_search_data.setdefault(section, []).extend(val)
                    else:
                        all_search_data[section] = val
            if page_num == 1 and "search_information" in page_data:
                all_search_data["search_information"] = page_data["search_information"]

        search_data = all_search_data

        products = len(search_data.get("organic_results", []))

        if has_product_sections:
            # Two-phase — one merged row per ASIN
            asins = extract_asins_from_search(search_data)[:args.max_asins]
            search_items_by_asin = {
                item.get("asin"): item
                for item in search_data.get("organic_results", [])
                if item.get("asin")
            }
            print(f"Fetching product data for {len(asins)} ASINs...")
            for asin in asins:
                try:
                    product_data = fetch_product(serpapi_key, asin, country=args.country)
                    search_item = search_items_by_asin.get(asin, {})
                    for table_mapping in mapping:
                        row = build_row_from_mapping(search_item, product_data, table_mapping)
                        if args.run_id:
                            row["run_id"] = args.run_id
                        if args.search_phrase:
                            row["search_phrase"] = args.search_phrase
                        if has_supabase:
                            supabase_insert(args.supabase_url, args.supabase_key,
                                            table_mapping["table"], row)
                        if has_csv:
                            if csv_output_is_dir:
                                csv_rows_by_table.setdefault(table_mapping["table"], []).append(row)
                            else:
                                csv_rows.append(row)
                    rows_saved += 1
                    time.sleep(0.3)
                except Exception as e:
                    print(f"WARNING: Failed for ASIN {asin}: {e}")
                    failed += 1
        else:
            # Search data only — one row per organic_result item
            items = search_data.get("organic_results", [])
            for item in items:
                try:
                    for table_mapping in mapping:
                        row = build_mapped_search_row(item, table_mapping)
                        if args.run_id:
                            row["run_id"] = args.run_id
                        if args.search_phrase:
                            row["search_phrase"] = args.search_phrase
                        if has_supabase:
                            supabase_insert(args.supabase_url, args.supabase_key,
                                            table_mapping["table"], row)
                        if has_csv:
                            if csv_output_is_dir:
                                csv_rows_by_table.setdefault(table_mapping["table"], []).append(row)
                            else:
                                csv_rows.append(row)
                    rows_saved += 1
                except Exception as e:
                    print(f"WARNING: Failed to save search row: {e}")
                    failed += 1

        if has_csv:
            if csv_output_is_dir:
                write_csv_by_table(csv_rows_by_table, args.csv_output, phrase_label)
            else:
                write_csv(csv_rows, args.csv_output)
        print(f"STATS:mode=search,search_phrase={phrase_label},"
              f"products={products},rows_saved={rows_saved},failed={failed}")


if __name__ == "__main__":
    main()
