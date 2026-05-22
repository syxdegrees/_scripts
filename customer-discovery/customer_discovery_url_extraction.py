#!/usr/bin/env python3
"""
customer_discovery.py
VOC discovery search — queries Supabase for search phrase templates,
fills in the discovery phrase, deduplicates, runs SerpAPI searches,
and saves results to Supabase.

Dependencies: pip install requests

Usage:
    python customer_discovery.py \
        --phrase "weight loss supplements" \
        --dimensions "anger,fear,frustration" \
        --scopes "1,2,3"
"""

import argparse
import os
import sys
import requests
from pathlib import Path

SERPAPI_URL = "https://serpapi.com/search"
AUTO_DIMENSIONS = ('forum', 'community', 'root', 'group')


def load_env():
    """Load .env from script folder first, then cwd, then rely on environment."""
    env_paths = [
        Path(__file__).parent / '.env',
        Path.cwd() / '.env',
    ]
    for env_path in env_paths:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, _, value = line.partition('=')
                        os.environ.setdefault(key.strip(), value.strip())
            break


def get_search_phrases(supabase_url, secret_key, dimensions, scopes):
    """
    Query Supabase for search_phrases matching:
      (dimension IN selected_dims AND scope IN selected_scopes)
      OR dimension IN (forum, community, root, group)
    """
    dims_str = ','.join(dimensions)
    scopes_str = ','.join(str(s) for s in scopes)
    auto_str = ','.join(AUTO_DIMENSIONS)

    or_filter = (
        f'(and(dimension.in.({dims_str}),scope.in.({scopes_str})),'
        f'dimension.in.({auto_str}))'
    )

    url = f"{supabase_url}/rest/v1/search_phrases"
    headers = {
        'apikey': secret_key,
        'Authorization': f'Bearer {secret_key}',
        'Content-Type': 'application/json',
    }
    params = {
        'or': or_filter,
        'select': 'id,search_phrase,dimension,scope',
    }

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    if not resp.ok:
        print(
            f"ERROR: Supabase query failed: {resp.status_code} {resp.text}",
            file=sys.stderr,
        )
        sys.exit(1)

    return resp.json()


def replace_placeholder(search_phrase, discovery_phrase):
    return search_phrase.replace('{discovery_phrase}', discovery_phrase)


def run_serp_search(api_key, term, engine):
    """Call SerpAPI and return list of {url, title, position} dicts."""
    params = {
        'engine': engine,
        'q': term,
        'api_key': api_key,
        'num': '10',
    }
    resp = requests.get(SERPAPI_URL, params=params, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"SerpAPI {engine} error {resp.status_code}: {resp.text}")

    data = resp.json()
    results = data.get('organic_results', [])
    return [
        {
            'url': r.get('link', ''),
            'title': r.get('title', ''),
            'position': i + 1,
        }
        for i, r in enumerate(results)
        if r.get('link')
    ]


def create_run(supabase_url, secret_key, phrase, dimensions, scopes):
    """Create a runs record and return its UUID."""
    url = f"{supabase_url}/rest/v1/runs"
    headers = {
        'apikey': secret_key,
        'Authorization': f'Bearer {secret_key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation',
    }
    payload = {
        'discovery_phrase': phrase,
        'dimensions': ','.join(dimensions),
        'scopes': ','.join(str(s) for s in scopes),
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if not resp.ok:
        print(
            f"ERROR: Failed to create run record: {resp.status_code} {resp.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    return resp.json()[0]['id']


def save_results(supabase_url, secret_key, rows):
    """Batch POST serp_results rows to Supabase."""
    url = f"{supabase_url}/rest/v1/serp_results"
    headers = {
        'apikey': secret_key,
        'Authorization': f'Bearer {secret_key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal',
    }
    resp = requests.post(url, headers=headers, json=rows, timeout=30)
    if not resp.ok:
        raise RuntimeError(
            f"Supabase insert failed: {resp.status_code} {resp.text}"
        )


def main():
    parser = argparse.ArgumentParser(description='VOC Customer Discovery Search')
    parser.add_argument('--phrase', required=True, help='Discovery search phrase')
    parser.add_argument('--dimensions', required=True,
                        help='Comma-separated dimension names')
    parser.add_argument('--scopes', required=True,
                        help='Comma-separated scope numbers (1-5)')
    args = parser.parse_args()

    load_env()

    serpapi_key = os.environ.get('SERPAPI_API_KEY', '')
    supabase_url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    supabase_key = os.environ.get('SUPABASE_SECRET_KEY', '')

    if not serpapi_key:
        print("ERROR: SERPAPI_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    if not supabase_url:
        print("ERROR: SUPABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    if not supabase_key:
        print("ERROR: SUPABASE_SECRET_KEY not set", file=sys.stderr)
        sys.exit(1)

    dimensions = [d.strip() for d in args.dimensions.split(',') if d.strip()]
    scopes = [int(s.strip()) for s in args.scopes.split(',') if s.strip()]
    phrase = args.phrase

    # 1. Create a run record
    run_id = create_run(supabase_url, supabase_key, phrase, dimensions, scopes)
    print(f"Run ID: {run_id}")

    # 2. Fetch search phrase templates
    rows = get_search_phrases(supabase_url, supabase_key, dimensions, scopes)

    if not rows:
        print(
            "ERROR: No search phrases found for the selected dimensions and scopes.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 3. Replace placeholder and deduplicate
    seen = set()
    unique_terms = []
    for row in rows:
        resolved = replace_placeholder(row['search_phrase'], phrase)
        if resolved not in seen:
            seen.add(resolved)
            unique_terms.append({'id': row['id'], 'term': resolved})

    total = len(unique_terms)
    urls_found = 0
    failed = 0

    engines = [
        ('google_light', 'google'),
        ('bing', 'bing'),
    ]

    # 4. SerpAPI loop
    for i, item in enumerate(unique_terms, 1):
        for engine, source in engines:
            print(f"Searching [{i}/{total}] ({source}): {item['term']}")
            try:
                results = run_serp_search(serpapi_key, item['term'], engine)
            except Exception as e:
                print(
                    f"WARNING: {source} search failed for '{item['term']}': {e}",
                    file=sys.stderr,
                )
                failed += 1
                continue

            if not results:
                continue

            # 5. Save to Supabase
            save_rows = [
                {
                    'run_id': run_id,
                    'search_phrase_id': item['id'],
                    'actual_search_phrase': item['term'],
                    'url': r['url'],
                    'title': r['title'],
                    'position': r['position'],
                    'source': source,
                }
                for r in results
            ]

            try:
                save_results(supabase_url, supabase_key, save_rows)
                urls_found += len(results)
            except Exception as e:
                print(
                    f"WARNING: Failed to save {source} results for '{item['term']}': {e}",
                    file=sys.stderr,
                )

    print(f"STATS:run_id={run_id},terms={total},urls_found={urls_found},failed={failed}")


if __name__ == '__main__':
    main()
