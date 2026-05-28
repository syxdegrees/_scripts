#!/usr/bin/env python3
"""
API refresh tool. Makes a live SerpAPI call for a given engine and compares the
response structure against the reference file. Reports MISSING / PARTIAL / OK per section.
Creates the reference file if it does not exist.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import load_env
from shared.api import serpapi_get
from shared.retry import with_retry

_REFERENCE_DIR = r"C:\Users\jeshj\Desktop\Coding\claude-skills\_shared"
_STRIP_KEYS = {"search_metadata", "search_parameters"}

_ENGINE_BASE_PARAMS = {
    "google_light":        {"engine": "google_light", "gl": "us", "hl": "en"},
    "google_ai_mode":      {"engine": "google_ai_mode", "gl": "us", "hl": "en", "continuable": False},
    "google_autocomplete": {"engine": "google_autocomplete", "gl": "us", "hl": "en", "client": "chrome"},
    "google_forums":       {"engine": "google_forums", "gl": "us", "hl": "en"},
    "google_jobs":         {"engine": "google_jobs", "gl": "us", "hl": "en"},
}


def _reference_path(engine_name):
    slug = engine_name.replace("_", "-")
    return os.path.join(_REFERENCE_DIR, f"serpapi-{slug}-api-reference.md")


def load_reference(engine_name):
    path = _reference_path(engine_name)
    if not os.path.exists(path):
        return {}
    sections = {}
    current = None
    with open(path) as f:
        for line in f:
            s = re.match(r"^## (.+)", line.strip())
            field = re.match(r"^\| `(.+?)` \|", line.strip())
            if s:
                current = s.group(1)
                sections[current] = set()
            elif field and current:
                sections[current].add(field.group(1))
    return sections


def _observed_keys(section_data):
    if isinstance(section_data, list) and section_data:
        first = section_data[0]
        if isinstance(first, dict):
            return set(first.keys())
        return set()
    if isinstance(section_data, dict):
        return set(section_data.keys())
    return set()


def check_engine(api_key, engine_name, search_phrase):
    params = {**_ENGINE_BASE_PARAMS[engine_name], "q": search_phrase}
    response = with_retry(lambda: serpapi_get(api_key, params))
    sections = {k: v for k, v in response.items() if k not in _STRIP_KEYS}
    reference = load_reference(engine_name)
    results = {}
    for name, data in sections.items():
        if name not in reference:
            results[name] = {"status": "MISSING", "missing_keys": []}
            continue
        observed = _observed_keys(data)
        missing = observed - reference[name]
        results[name] = {
            "status": "PARTIAL" if missing else "OK",
            "missing_keys": sorted(missing),
        }
    return results, sections


def write_reference(engine_name, sections, existing_reference):
    path = _reference_path(engine_name)
    slug = engine_name.replace("_", "-")
    lines = [f"# SerpAPI {slug} API Reference\n\n"]
    for section_name, data in sections.items():
        lines.append(f"## {section_name}\n\n")
        existing_keys = existing_reference.get(section_name, set())
        observed = _observed_keys(data)
        all_keys = existing_keys | observed
        if all_keys:
            lines.append("| Field | Notes |\n|-------|-------|\n")
            for key in sorted(all_keys):
                lines.append(f"| `{key}` | |\n")
        lines.append("\n")
    with open(path, "w") as f:
        f.writelines(lines)
    print(f"Reference written: {path}")


def main():
    parser = argparse.ArgumentParser(description="SerpAPI reference refresh tool")
    parser.add_argument("--engine", required=True, choices=list(_ENGINE_BASE_PARAMS.keys()))
    parser.add_argument("--search_phrase", required=True)
    parser.add_argument("--update", action="store_true",
                        help="Update reference file if MISSING or PARTIAL sections found")
    args = parser.parse_args()

    load_env()
    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        print("ERROR: SERPAPI_API_KEY not found in environment or .env")
        sys.exit(1)

    print(f"Checking {args.engine} with phrase: {args.search_phrase}")
    results, raw_sections = check_engine(api_key, args.engine, args.search_phrase)

    has_issues = any(r["status"] != "OK" for r in results.values())
    for section, info in results.items():
        tag = f"  missing keys: {info['missing_keys']}" if info["missing_keys"] else ""
        print(f"  {info['status']:8s} {section}{tag}")

    if not has_issues:
        print("Reference is up to date.")
        return

    if args.update:
        existing = load_reference(args.engine)
        write_reference(args.engine, raw_sections, existing)
    else:
        print("\nRun with --update to update the reference file.")


if __name__ == "__main__":
    main()
