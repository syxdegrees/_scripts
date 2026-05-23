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


def load_mapping(path):
    """Load field mapping JSON. Exits with ERROR if missing or malformed."""
    try:
        with open(path, encoding="utf-8") as f:
            mapping = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Mapping file not found: {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Mapping file is not valid JSON: {e}")
        sys.exit(1)
    if not isinstance(mapping, dict):
        print(f"ERROR: Mapping file must be a JSON object (got {type(mapping).__name__})")
        sys.exit(1)
    return mapping


def apply_mapping(row, mapping):
    """Transform a row using the field mapping.

    For each (api_field -> col_name) in mapping: if api_field is in row,
    include it as col_name in the output.
    Fields in row not in mapping are dropped with a WARNING (printed once per field).
    run_id is always forwarded — mapped to its col_name if present in mapping,
    otherwise kept as 'run_id'.
    """
    mapped = {}
    warned = set()

    for api_field, col_name in mapping.items():
        if api_field in row:
            mapped[col_name] = row[api_field]

    for field in row:
        if field == "run_id":
            continue
        if field not in mapping and field not in warned:
            print(f"WARNING: Field '{field}' not in mapping — dropped")
            warned.add(field)

    if row.get("run_id") is not None:
        run_id_col = mapping.get("run_id", "run_id")
        mapped[run_id_col] = row["run_id"]

    return mapped


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


def export_voc_rows(supabase_url, supabase_key, voc_table, asin, product_title,
                    run_id, reviews_information):
    """Export VoC rows from reviews_information to the voc_content table.

    Writes:
      - One row for the overall AI summary text (if present)
      - One row per insight example snippet (actual customer quote + sentiment)
    Returns count of rows saved.
    """
    saved = 0
    if not reviews_information:
        return saved

    summary = reviews_information.get("summary", {})

    # Overall AI summary paragraph
    summary_text = summary.get("text")
    if summary_text:
        try:
            supabase_insert(supabase_url, supabase_key, voc_table, {
                "run_id": run_id,
                "body": summary_text,
                "content_type": "review",
                "source": "amazon",
                "title": product_title,
                "asin": asin,
            })
            saved += 1
        except Exception as e:
            print(f"WARNING: VoC summary insert failed for '{product_title}': {e}")

    # Individual insight example snippets
    for insight in summary.get("insights", []):
        sentiment = insight.get("sentiment", "")
        for example in insight.get("examples", []):
            snippet = example.get("snippet", "").strip()
            if not snippet:
                continue
            try:
                supabase_insert(supabase_url, supabase_key, voc_table, {
                    "run_id": run_id,
                    "body": snippet,
                    "content_type": "review",
                    "source": "amazon",
                    "title": product_title,
                    "asin": asin,
                    "sentiment": sentiment or None,
                })
                saved += 1
            except Exception as e:
                print(f"WARNING: VoC snippet insert failed for '{product_title}': {e}")

    return saved


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


def write_csv(rows, path):
    import csv
    if not rows:
        print("WARNING: No rows to write to CSV.")
        return
    fieldnames = list(dict.fromkeys(k for row in rows for k in row))
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV written: {path} ({len(rows)} rows)")


def main():
    parser = argparse.ArgumentParser(description="Amazon SerpAPI extractor")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--search_phrase", help="Keyword to search on Amazon")
    group.add_argument("--asin", help="Amazon ASIN for direct product lookup")
    parser.add_argument("--sections", required=True,
                        help="Comma-separated section names to fetch")
    parser.add_argument("--table", default=None,
                        help="Supabase table name to write results to")
    parser.add_argument("--supabase_url", default=None,
                        help="Supabase project URL")
    parser.add_argument("--supabase_key", default=None,
                        help="Supabase service role key")
    parser.add_argument("--csv_output", default=None,
                        help="Local CSV file path for testing (no Supabase required)")
    parser.add_argument("--run_id", default=None,
                        help="Optional run UUID for linking results")
    parser.add_argument("--max_asins", type=int, default=10,
                        help="Max ASINs to fetch in two-stage mode (default: 10)")
    parser.add_argument("--country", default="amazon.com",
                        help="Amazon domain (e.g. amazon.com, amazon.co.uk)")
    parser.add_argument("--pages", type=int, default=1,
                        help="Number of search result pages to fetch (default: 1)")
    parser.add_argument("--mapping", required=True,
                        help="Path to JSON mapping file (api_field -> column_name)")
    args = parser.parse_args()

    if args.country not in VALID_DOMAINS:
        print(f"ERROR: Invalid country '{args.country}'. Must be one of: {', '.join(sorted(VALID_DOMAINS))}")
        sys.exit(1)

    has_supabase = all([args.supabase_url, args.supabase_key, args.table])
    has_csv = bool(args.csv_output)
    if not has_supabase and not has_csv:
        print("ERROR: Provide either --csv_output or all three Supabase args (--supabase_url, --supabase_key, --table).")
        sys.exit(1)
    if any([args.supabase_url, args.supabase_key, args.table]) and not has_supabase:
        print("ERROR: --supabase_url, --supabase_key, and --table must all be provided together.")
        sys.exit(1)

    load_env()

    serpapi_key = os.environ.get("SERPAPI_API_KEY")
    if not serpapi_key:
        print("ERROR: SERPAPI_API_KEY is not set in environment or .env file.")
        sys.exit(1)

    mapping = load_mapping(args.mapping)

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

    if args.asin:
        # --- ASIN mode ---
        phrase_label = f"ASIN:{args.asin}"
        print(f"Fetching product page for ASIN {args.asin}...")
        try:
            product_data = fetch_product(serpapi_key, args.asin, country=args.country)
            row = build_product_row(
                args.asin, product_data, requested_sections,
                args.run_id, None
            )
            mapped_row = apply_mapping(row, mapping)
            if has_supabase:
                supabase_insert(args.supabase_url, args.supabase_key, args.table, mapped_row)
            if has_csv:
                csv_rows.append(mapped_row)
            rows_saved += 1
        except Exception as e:
            print(f"WARNING: Failed to fetch/save ASIN {args.asin}: {e}")
            failed += 1

        if has_csv:
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

        # Save search-level sections
        search_rows = build_search_rows(
            args.search_phrase, search_data, requested_sections, args.run_id
        )
        for row in search_rows:
            try:
                mapped_row = apply_mapping(row, mapping)
                if has_supabase:
                    supabase_insert(
                        args.supabase_url, args.supabase_key, args.table, mapped_row
                    )
                if has_csv:
                    csv_rows.append(mapped_row)
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
                    product_data = fetch_product(serpapi_key, asin, country=args.country)
                    row = build_product_row(
                        asin, product_data, requested_sections,
                        args.run_id, args.search_phrase
                    )
                    mapped_row = apply_mapping(row, mapping)
                    if has_supabase:
                        supabase_insert(
                            args.supabase_url, args.supabase_key, args.table, mapped_row
                        )
                    if has_csv:
                        csv_rows.append(mapped_row)
                    rows_saved += 1
                    time.sleep(0.3)
                except Exception as e:
                    print(f"WARNING: Failed to fetch/save ASIN {asin}: {e}")
                    failed += 1

        if has_csv:
            write_csv(csv_rows, args.csv_output)
        print(f"STATS:mode=search,search_phrase={phrase_label},"
              f"products={products},rows_saved={rows_saved},failed={failed}")


if __name__ == "__main__":
    main()
