#!/usr/bin/env python3
"""
SerpAPI engine refresh script for skill-serpapi-search.

Calls SerpAPI for a given engine, writes a ref doc and CSV snapshot
to the installed skill's ref/ directory.

Usage:
    python serpapi_refresh.py --engine google --api-key KEY \\
        --skill-root "C:\\...\\skill-serpapi-search" --date 2026-05-29
"""

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

import requests


# ---------------------------------------------------------------------------
# Default search phrases per engine ID.
# Engines not listed here fall back to --query (default: "coffee").
# ---------------------------------------------------------------------------
PHRASES: dict[str, str] = {
    # Generic keyword
    "google": "coffee",
    "google_light": "coffee",
    "google_images": "coffee",
    "google_images_light": "coffee",
    "google_short_videos": "coffee",
    "google_news": "coffee",
    "google_news_light": "coffee",
    "google_autocomplete": "coffee",
    "google_trends": "coffee",
    "google_trends_autocomplete": "coffee",
    "bing": "coffee",
    "bing_images": "coffee",
    "bing_news": "coffee",
    "duckduckgo": "coffee",
    "duckduckgo_light": "coffee",
    "duckduckgo_news": "coffee",
    "yahoo": "coffee",
    "yahoo_images": "coffee",
    "yahoo_videos": "coffee",
    "yandex": "coffee",
    "yandex_videos": "coffee",
    "yandex_images": "coffee",
    "baidu": "coffee",
    "baidu_news": "coffee",
    "naver": "coffee",
    # Product / shopping
    "google_shopping": "coffee maker",
    "google_shopping_light": "coffee maker",
    "google_patents": "coffee maker",
    "amazon": "coffee maker",
    "ebay": "coffee maker",
    "walmart": "coffee maker",
    "bing_shopping": "coffee maker",
    "yahoo_shopping": "coffee maker",
    "home_depot": "coffee maker",
    # Local / map
    "google_local": "coffee shops",
    "google_maps": "coffee shops",
    "google_maps_autocomplete": "coffee shops",
    "apple_maps": "coffee shops",
    "duckduckgo_maps": "coffee shops",
    "bing_maps": "coffee shops",
    "yelp": "coffee shops",
    "tripadvisor": "coffee shops",
    # AI / conversational
    "google_ai_mode": "what are the health benefits of coffee",
    "bing_copilot": "what are the health benefits of coffee",
    "brave_ai_mode": "what are the health benefits of coffee",
    "naver_ai_overview": "what are the health benefits of coffee",
    # Video
    "google_videos": "coffee brewing tutorial",
    "google_videos_light": "coffee brewing tutorial",
    "bing_videos": "coffee brewing tutorial",
    "youtube": "coffee brewing tutorial",
    # Forum / academic
    "google_forums": "best coffee beans",
    "google_scholar": "coffee health effects",
    # Jobs / events
    "google_jobs": "barista",
    "google_events": "coffee festivals in Austin TX",
    # App / media stores
    "google_play": "coffee",
    "apple_app_store": "coffee",
    "google_play_books": "coffee",
    "google_play_games": "puzzle",
    "google_play_movies": "comedy",
    # Finance / autocompletes
    "google_finance": "AAPL:NASDAQ",
    "google_flights_autocomplete": "New York",
    "google_hotels_autocomplete": "Hilton",
}

# ---------------------------------------------------------------------------
# Query parameter name per engine.
# Engines not listed here use "q" (the SerpAPI default).
# ---------------------------------------------------------------------------
QUERY_PARAM: dict[str, str] = {
    "amazon": "k",
    "apple_app_store": "term",
    "apple_maps": "query",
    "ebay": "_nkw",
    "naver": "query",
    "naver_ai_overview": "query",
    "walmart": "query",
    "yahoo": "p",
    "yahoo_shopping": "p",
    "yahoo_videos": "p",
    "yahoo_images": "p",
    "yandex": "text",
    "yandex_videos": "text",
    "yandex_images": "text",
    "yelp": "find_desc",
    "youtube": "search_query",
}

# ---------------------------------------------------------------------------
# Extra params merged into the API call for engines that need more than q=...
# ---------------------------------------------------------------------------
EXTRA_PARAMS: dict[str, dict] = {
    "google_maps": {"type": "search", "ll": "@40.7128,-74.0060,14z"},
    "google_maps_autocomplete": {"ll": "@40.7128,-74.0060,14z"},
    "google_local": {"location": "Austin, Texas, United States"},
    "google_trends": {"data_type": "TIMESERIES"},
    "yelp": {"find_loc": "Austin, Texas"},
    "apple_maps": {"location": "Austin, Texas, United States"},
    "duckduckgo_maps": {"location": "Austin, Texas, United States"},
    "bing_maps": {"location": "Austin, Texas, United States"},
}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def engine_to_slug(engine_id: str) -> str:
    """google_light -> google-light"""
    return engine_id.replace("_", "-")


def get_type_label(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def build_field_table(data: dict) -> list[dict]:
    """
    Walk JSON response and return field rows for the ref doc markdown table.
    Each row: {"path": str, "type": str, "example": str}
    Arrays of objects are shown with [] notation using the first item's fields.
    """
    rows: list[dict] = []

    def walk(obj, prefix: str = "") -> None:
        if not isinstance(obj, dict):
            return
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                walk(value, path)
            elif isinstance(value, list):
                arr_path = f"{path}[]"
                if not value:
                    rows.append({"path": arr_path, "type": "array", "example": "(empty)"})
                elif isinstance(value[0], dict):
                    rows.append({"path": arr_path, "type": "array of objects", "example": f"({len(value)} items)"})
                    walk(value[0], arr_path)
                else:
                    rows.append({"path": arr_path, "type": f"array of {get_type_label(value[0])}s", "example": str(value[0])[:80]})
            else:
                example = "" if value is None else str(value)[:80]
                rows.append({"path": path, "type": get_type_label(value), "example": example})

    walk(data)
    return rows


def flatten_value(obj, prefix: str = "") -> dict:
    """
    Recursively flatten a JSON value to {dot.notation.key: scalar} pairs.
    Used to produce CSV rows.
    """
    result: dict = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            child = f"{prefix}.{k}" if prefix else k
            result.update(flatten_value(v, child))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            child = f"{prefix}.{i}" if prefix else str(i)
            result.update(flatten_value(v, child))
    else:
        result[prefix] = obj
    return result


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def call_serpapi(engine_id: str, api_key: str, fallback_query: str) -> dict:
    query = PHRASES.get(engine_id, fallback_query)
    query_param = QUERY_PARAM.get(engine_id, "q")
    params: dict = {
        "engine": engine_id,
        query_param: query,
        "api_key": api_key,
        "no_cache": "true",
    }
    params.update(EXTRA_PARAMS.get(engine_id, {}))
    resp = requests.get("https://serpapi.com/search.json", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_ref_doc(skill_root: Path, engine_id: str, refresh_date: str, data: dict) -> None:
    slug = engine_to_slug(engine_id)
    query = PHRASES.get(engine_id, "coffee")
    display_name = engine_id.replace("_", " ").title()

    ref_dir = skill_root / "_ref"
    ref_dir.mkdir(parents=True, exist_ok=True)
    doc_path = ref_dir / f"serpapi-search-reference-{slug}.md"

    error = data.get("error") if data else "Empty response"
    if error or not data:
        doc_path.write_text(
            f"# SerpAPI Engine Reference — {display_name}\n\n"
            f"**Engine ID:** `{engine_id}`\n"
            f"**Last Updated:** {refresh_date}\n"
            f"**Refresh Query:** `\"{query}\"`\n\n"
            "---\n\n## Status\n\n"
            f"**ERROR:** {error}\n\nNo response fields available.\n",
            encoding="utf-8",
        )
        return

    fields = build_field_table(data)
    top_keys = ", ".join(f"`{k}`" for k in data.keys())
    table_rows = "\n".join(
        "| {} | {} | {} | |".format(f["path"], f["type"], f["example"].replace("|", "\\|"))
        for f in fields
    )

    doc_path.write_text(
        f"# SerpAPI Engine Reference — {display_name}\n\n"
        f"**Engine ID:** `{engine_id}`\n"
        f"**Last Updated:** {refresh_date}\n"
        f"**Refresh Query:** `\"{query}\"`\n\n"
        "---\n\n## Response Fields\n\n"
        "| Field Path | Type | Example Value | Notes |\n"
        "|------------|------|---------------|-------|\n"
        f"{table_rows}\n\n"
        "---\n\n## Top-Level Keys Present in This Response\n\n"
        f"{top_keys}\n",
        encoding="utf-8",
    )


def write_csv(skill_root: Path, engine_id: str, refresh_date: str, data: dict) -> None:
    slug = engine_to_slug(engine_id)
    data_dir = skill_root / "_ref" / "_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    csv_path = data_dir / f"{refresh_date}-serpapi-search-reference-{slug}-data.csv"

    rows: list[dict] = []
    for section, value in (data or {}).items():
        if isinstance(value, list):
            for i, item in enumerate(value):
                flat = flatten_value(item) if isinstance(item, dict) else {"value": str(item)}
                rows.append({"_section": section, "_index": i, **flat})
        elif isinstance(value, dict):
            flat = flatten_value(value)
            rows.append({"_section": section, "_index": 0, **flat})
        else:
            rows.append({"_section": section, "_index": 0, "value": str(value)})

    all_keys: set[str] = set()
    for r in rows:
        all_keys.update(r.keys())

    fieldnames = ["_section", "_index"] + sorted(k for k in all_keys if k not in {"_section", "_index"})

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="SerpAPI engine refresh")
    parser.add_argument("--engine", required=True, help="SerpAPI engine ID (e.g. google, amazon)")
    parser.add_argument("--api-key", required=True, dest="api_key", help="SerpAPI API key")
    parser.add_argument("--skill-root", required=True, dest="skill_root",
                        help="Absolute path to installed skill-serpapi-search folder")
    parser.add_argument("--query", default="coffee",
                        help="Fallback query for engines not in PHRASES dict")
    parser.add_argument("--date", default=str(date.today()),
                        help="Date string for output filenames (YYYY-MM-DD)")
    args = parser.parse_args()

    if not args.api_key.strip():
        print(f"ERROR: {args.engine} — SERPAPI_API_KEY is not set")
        sys.exit(1)

    skill_root = Path(args.skill_root)

    try:
        data = call_serpapi(args.engine, args.api_key, args.query)
        write_ref_doc(skill_root, args.engine, args.date, data)
        write_csv(skill_root, args.engine, args.date, data)
        print(f"SUCCESS: {args.engine}")
        sys.exit(0)
    except requests.exceptions.Timeout:
        print(f"ERROR: {args.engine} — Network timeout after 30s")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: {args.engine} — HTTP {e.response.status_code}: {e.response.text[:200]}")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {args.engine} — {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
