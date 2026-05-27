#!/usr/bin/env python3
"""
Full API test: dumps raw SerpAPI search + product + reviews responses to dated CSVs.
No mapping, no Supabase, no field filtering.

Output:
  tests/YYYY-MM-DD_full-api-test_search_{term}.csv
  tests/YYYY-MM-DD_full-api-test_product_{product_id}.csv
  tests/YYYY-MM-DD_full-api-test_reviews_{product_id}.csv
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
            result[section] = set(first.keys()) if isinstance(first, dict) else set()
        elif isinstance(value, dict):
            result[section] = set(value.keys())
        else:
            result[section] = set()
    return result


def check_against_reference(
    search_response: dict,
    product_response: dict,
    reviews_response: dict,
    reference_path: str,
) -> None:
    ref_path = Path(reference_path)
    if not ref_path.exists():
        print(f"ERROR: Reference file not found: {reference_path}")
        sys.exit(1)
    ref = ref_path.read_text(encoding="utf-8")

    search_keys = collect_section_keys(search_response)
    product_keys = collect_section_keys(product_response)
    reviews_keys = collect_section_keys(reviews_response)

    any_issues = False

    print("\nRefresh API Reference Check")
    print("=" * 60)

    for api_label, sections in [
        ("Search API  (engine=home_depot)", search_keys),
        ("Product API (engine=home_depot_product)", product_keys),
        ("Reviews API (engine=home_depot_product_reviews)", reviews_keys),
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
        print("Action: update serpapi-home-depot-api-reference.md to add the entries above.")
    else:
        print("Reference is up to date — no missing sections or keys found.")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Full API test — dumps raw SerpAPI responses to dated CSVs, or checks field coverage against a reference file"
    )
    parser.add_argument("--search_phrase", required=True, help="Search term to test with")
    parser.add_argument(
        "--refresh_reference",
        metavar="PATH",
        help="Path to serpapi-home-depot-api-reference.md. When set, checks live API keys against the reference instead of writing CSVs.",
    )
    args = parser.parse_args()

    load_env()
    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        print("ERROR: SERPAPI_API_KEY not found in environment or .env")
        sys.exit(1)

    clean_term = clean_search_term(args.search_phrase)

    # Search API
    print(f"Calling search API: {args.search_phrase}")
    search_response = serpapi_get(api_key, {
        "engine": "home_depot",
        "q": args.search_phrase,
        "country": "us",
        "page": 1,
    })

    # Extract first product_id
    products = search_response.get("products", [])
    if not products:
        print("WARNING: No products in search response — skipping product and reviews API calls.")
        if args.refresh_reference:
            check_against_reference(search_response, {}, {}, args.refresh_reference)
        return
    product_id = str(products[0].get("product_id", ""))
    if not product_id:
        print("WARNING: First product has no product_id — skipping product and reviews API calls.")
        if args.refresh_reference:
            check_against_reference(search_response, {}, {}, args.refresh_reference)
        return

    # Product API
    print(f"Calling product API: {product_id}")
    product_response = serpapi_get(api_key, {
        "engine": "home_depot_product",
        "product_id": product_id,
    })

    # Reviews API
    print(f"Calling reviews API: {product_id}")
    reviews_response = serpapi_get(api_key, {
        "engine": "home_depot_product_reviews",
        "product_id": product_id,
    })

    if args.refresh_reference:
        check_against_reference(search_response, product_response, reviews_response, args.refresh_reference)
        return

    search_rows = flatten_response(search_response)
    search_path = TESTS_DIR / build_filename("search", clean_term)
    write_csv(search_rows, search_path)

    product_rows = flatten_response(product_response, extra_cols={"product_id": product_id})
    product_path = TESTS_DIR / build_filename("product", product_id)
    write_csv(product_rows, product_path)

    reviews_rows = flatten_response(reviews_response, extra_cols={"product_id": product_id})
    reviews_path = TESTS_DIR / build_filename("reviews", product_id)
    write_csv(reviews_rows, reviews_path)

    print(f"""
Full API Test complete.
────────────────────────────────────────
  Search term  : {args.search_phrase}
  Product ID   : {product_id}
  Search rows  : {len(search_rows)}  →  {search_path}
  Product rows : {len(product_rows)}  →  {product_path}
  Reviews rows : {len(reviews_rows)}  →  {reviews_path}
────────────────────────────────────────
Review the CSV files to explore the full API surface.
""")


if __name__ == "__main__":
    main()
