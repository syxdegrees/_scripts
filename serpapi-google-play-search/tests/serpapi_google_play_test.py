#!/usr/bin/env python3
"""
Full API test: dumps raw SerpAPI search + product (no reviews) + product (with reviews) responses to dated CSVs.
No mapping, no Supabase, no field filtering.

Output:
  tests/YYYY-MM-DD_full-api-test_search_{term}.csv
  tests/YYYY-MM-DD_full-api-test_product_{product_id}.csv
  tests/YYYY-MM-DD_full-api-test_product_reviews_{product_id}.csv
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SERPAPI_URL = "https://serpapi.com/search"
TESTS_DIR = Path(__file__).parent

SEARCH_ENGINES = {
    "apps":   "google_play",
    "games":  "google_play_games",
    "movies": "google_play_movies",
    "books":  "google_play_books",
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


def clean_search_term(term: str) -> str:
    term = term.lower().strip()
    term = re.sub(r"\s+", "-", term)
    term = re.sub(r"[^a-z0-9-]", "", term)
    term = re.sub(r"-+", "-", term)
    return term.strip("-")


def build_filename(test_type: str, identifier: str) -> str:
    today = date.today().strftime("%Y-%m-%d")
    return f"{today}_full-api-test_{test_type}_{identifier}.csv"


def serpapi_get(api_key: str, params: dict) -> dict:
    try:
        import requests
    except ImportError:
        print("ERROR: requests library not installed. Run: pip install requests")
        sys.exit(1)
    resp = requests.get(SERPAPI_URL, params={**params, "api_key": api_key}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def flatten_response(response: dict, extra_cols: dict = None) -> list:
    rows = []
    for section, value in response.items():
        if isinstance(value, list):
            for i, item in enumerate(value):
                row = {"section": section, "item_index": i, "data": json.dumps(item, ensure_ascii=False)}
                if extra_cols:
                    row = {**extra_cols, **row}
                rows.append(row)
        else:
            row = {"section": section, "item_index": 0, "data": json.dumps(value, ensure_ascii=False)}
            if extra_cols:
                row = {**extra_cols, **row}
            rows.append(row)
    return rows


def write_csv(rows: list, path: Path) -> None:
    if not rows:
        print("WARNING: No rows to write.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Written: {path} ({len(rows)} rows)")


METADATA_KEYS = {
    "search_metadata", "search_parameters", "search_information",
    "serpapi_pagination", "pagination", "error",
}


def collect_section_keys(response: dict) -> dict:
    """Returns {section: set_of_sub_keys} for all non-metadata sections."""
    result = {}
    for section, value in response.items():
        if section in METADATA_KEYS:
            continue
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, dict):
                # For nested organic_results (sections → items), descend one level
                items = first.get("items", None)
                if items and isinstance(items, list) and items:
                    result[section] = set(items[0].keys()) if isinstance(items[0], dict) else set()
                else:
                    result[section] = set(first.keys())
            else:
                result[section] = set()
        elif isinstance(value, dict):
            result[section] = set(value.keys())
        else:
            result[section] = set()
    return result


def extract_first_product_id(organic_results: list) -> str | None:
    """Flatten nested sections → items and return first product_id found."""
    for section in organic_results:
        for item in section.get("items", []):
            pid = item.get("product_id")
            if pid:
                return pid
    return None


def check_against_reference(
    search_response: dict,
    product_response: dict,
    product_reviews_response: dict,
    reference_path: str,
    store_type: str,
) -> None:
    ref_path = Path(reference_path)
    if not ref_path.exists():
        print(f"ERROR: Reference file not found: {reference_path}")
        sys.exit(1)
    ref = ref_path.read_text(encoding="utf-8")

    search_keys = collect_section_keys(search_response)
    product_keys = collect_section_keys(product_response)
    reviews_keys = collect_section_keys(product_reviews_response)

    engine = SEARCH_ENGINES.get(store_type, "google_play")
    any_issues = False

    print("\nRefresh API Reference Check")
    print("=" * 60)

    for api_label, sections in [
        (f"Search API  (engine={engine})", search_keys),
        ("Product API (engine=google_play_product, no reviews)", product_keys),
        ("Product API (engine=google_play_product, all_reviews=true)", reviews_keys),
    ]:
        print(f"\n{api_label}")
        print("-" * 50)
        missing_sections = []
        partial_sections = []
        ok_sections = []

        for section in sorted(sections):
            subkeys = sections[section]
            if f"`{section}`" not in ref:
                missing_sections.append(section)
                any_issues = True
                continue
            missing_sub = sorted(k for k in subkeys if f"`{k}`" not in ref)
            if missing_sub:
                partial_sections.append((section, missing_sub))
                any_issues = True
            else:
                ok_sections.append(section)

        for s in ok_sections:
            print(f"  OK       {s}")
        for s in missing_sections:
            print(f"  MISSING  {s}  ← entire section not documented")
        for s, keys in partial_sections:
            print(f"  PARTIAL  {s}")
            for k in keys:
                print(f"             missing key: `{k}`")

    print("\n" + "=" * 60)
    if any_issues:
        print("Action: update serpapi-google-play-api-reference.md to add the entries above.")
    else:
        print("Reference is up to date — no missing sections or keys found.")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Full API test — dumps raw SerpAPI responses to dated CSVs, or checks field coverage against a reference file"
    )
    parser.add_argument("--search_phrase", required=True, help="Search term to test with")
    parser.add_argument(
        "--store_type", default="apps",
        choices=["apps", "games", "movies", "books"],
        help="Store type for search engine selection (default: apps)",
    )
    parser.add_argument("--gl", default="us", help="Country code (default: us)")
    parser.add_argument("--hl", default="en", help="Language code (default: en)")
    parser.add_argument(
        "--refresh_reference",
        metavar="PATH",
        help="Path to serpapi-google-play-api-reference.md. When set, checks live API against the reference instead of writing CSVs.",
    )
    args = parser.parse_args()

    load_env()
    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        print("ERROR: SERPAPI_API_KEY not found in environment or .env")
        sys.exit(1)

    engine = SEARCH_ENGINES[args.store_type]
    clean_term = clean_search_term(args.search_phrase)

    # Call 1: Search API
    print(f"Calling search API ({engine}): {args.search_phrase}")
    search_response = serpapi_get(api_key, {
        "engine": engine,
        "q": args.search_phrase,
        "gl": args.gl,
        "hl": args.hl,
    })

    # Extract first product_id from nested organic_results
    organic = search_response.get("organic_results", [])
    if not organic:
        print("WARNING: No organic_results in search response — skipping product API calls.")
        if args.refresh_reference:
            check_against_reference(search_response, {}, {}, args.refresh_reference, args.store_type)
        return
    product_id = extract_first_product_id(organic)
    if not product_id:
        print("WARNING: No product_id found in results — skipping product API calls.")
        if args.refresh_reference:
            check_against_reference(search_response, {}, {}, args.refresh_reference, args.store_type)
        return

    # Call 2: Product API (no reviews)
    print(f"Calling product API (no reviews): {product_id}")
    product_response = serpapi_get(api_key, {
        "engine": "google_play_product",
        "product_id": product_id,
        "store": args.store_type,
        "gl": args.gl,
        "hl": args.hl,
    })

    # Call 3: Product API (with reviews)
    print(f"Calling product API (all_reviews=true): {product_id}")
    product_reviews_response = serpapi_get(api_key, {
        "engine": "google_play_product",
        "product_id": product_id,
        "store": args.store_type,
        "gl": args.gl,
        "hl": args.hl,
        "all_reviews": "true",
    })

    if args.refresh_reference:
        check_against_reference(
            search_response, product_response, product_reviews_response,
            args.refresh_reference, args.store_type,
        )
        return

    search_rows = flatten_response(search_response)
    search_path = TESTS_DIR / build_filename("search", clean_term)
    write_csv(search_rows, search_path)

    product_rows = flatten_response(product_response, extra_cols={"product_id": product_id})
    product_path = TESTS_DIR / build_filename("product", product_id)
    write_csv(product_rows, product_path)

    reviews_rows = flatten_response(product_reviews_response, extra_cols={"product_id": product_id})
    reviews_path = TESTS_DIR / build_filename("product-reviews", product_id)
    write_csv(reviews_rows, reviews_path)

    print(f"""
Full API Test complete.
────────────────────────────────────────
  Search term    : {args.search_phrase}
  Store type     : {args.store_type}
  Product ID     : {product_id}
  Search rows    : {len(search_rows)}  →  {search_path}
  Product rows   : {len(product_rows)}  →  {product_path}
  Reviews rows   : {len(reviews_rows)}  →  {reviews_path}
────────────────────────────────────────
Review the CSV files to explore the full API surface.
""")


if __name__ == "__main__":
    main()
