#!/usr/bin/env python3
"""
Full API test: dumps raw SerpAPI search + product responses to dated CSVs.
No mapping, no Supabase, no field filtering.

Output:
  tests/YYYY-MM-DD_full-api-test_search_{term}.csv
  tests/YYYY-MM-DD_full-api-test_product_{asin}.csv
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

SERPAPI_URL = "https://serpapi.com/search"
TESTS_DIR = Path(__file__).parent / "tests"


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


def main():
    parser = argparse.ArgumentParser(
        description="Full API test — dumps raw SerpAPI response to dated CSVs"
    )
    parser.add_argument("--search_phrase", required=True, help="Search term to test with")
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
        "engine": "amazon",
        "k": args.search_phrase,
        "amazon_domain": "amazon.com",
        "page": 1,
    })
    search_rows = flatten_response(search_response)
    search_filename = build_filename("search", clean_term)
    search_path = TESTS_DIR / search_filename
    write_csv(search_rows, search_path)

    # Extract first ASIN
    organic = search_response.get("organic_results", [])
    if not organic:
        print("WARNING: No organic_results — skipping product API call.")
        return
    asin = organic[0].get("asin")
    if not asin:
        print("WARNING: First organic result has no ASIN — skipping product API call.")
        return

    # Product API
    print(f"Calling product API: {asin}")
    product_response = serpapi_get(api_key, {
        "engine": "amazon_product",
        "asin": asin,
        "amazon_domain": "amazon.com",
    })
    product_rows = flatten_response(product_response, extra_cols={"asin": asin})
    product_filename = build_filename("product", asin)
    product_path = TESTS_DIR / product_filename
    write_csv(product_rows, product_path)

    print(f"""
Full API Test complete.
────────────────────────────────────────
  Search term : {args.search_phrase}
  ASIN tested : {asin}
  Search rows : {len(search_rows)}  →  {search_path}
  Product rows: {len(product_rows)}  →  {product_path}
────────────────────────────────────────
Review the CSV files to explore the full API surface.
""")


if __name__ == "__main__":
    main()
