#!/usr/bin/env python3
"""
customer_discovery_yelp_voc_extraction.py
Searches Yelp for a run's discovery phrase, fetches business reviews,
and saves to yelp_businesses, yelp_reviews, and voc_content.

Dependencies: pip install requests

Usage:
    python customer_discovery_yelp_voc_extraction.py --run_id <uuid>
"""

import argparse
import os
import sys
import requests
from pathlib import Path

SERPAPI_URL = "https://serpapi.com/search"


def load_env():
    for env_path in [Path(__file__).parent / '.env', Path.cwd() / '.env']:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, _, value = line.partition('=')
                        os.environ.setdefault(key.strip(), value.strip())
            break


def supabase_insert(supabase_url, secret_key, table, row, return_id=False):
    headers = {
        'apikey': secret_key,
        'Authorization': f'Bearer {secret_key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation' if return_id else 'return=minimal',
    }
    resp = requests.post(
        f"{supabase_url}/rest/v1/{table}",
        headers=headers,
        json=row,
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Insert {table} failed: {resp.status_code} {resp.text}")
    return resp.json()[0]['id'] if return_id else None


def get_discovery_phrase(supabase_url, secret_key, run_id):
    resp = requests.get(
        f"{supabase_url}/rest/v1/runs",
        headers={'apikey': secret_key, 'Authorization': f'Bearer {secret_key}'},
        params={'id': f'eq.{run_id}', 'select': 'discovery_phrase'},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Supabase query failed: {resp.status_code} {resp.text}")
    rows = resp.json()
    if not rows:
        print(f"ERROR: run_id {run_id} not found", file=sys.stderr)
        sys.exit(1)
    return rows[0]['discovery_phrase']


def search_yelp(serpapi_key, phrase):
    resp = requests.get(
        SERPAPI_URL,
        params={'engine': 'yelp', 'find_desc': phrase, 'api_key': serpapi_key},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"SerpAPI yelp error {resp.status_code}: {resp.text}")
    return resp.json().get('organic_results', [])


def fetch_reviews(serpapi_key, place_id):
    resp = requests.get(
        SERPAPI_URL,
        params={
            'engine': 'yelp_reviews',
            'place_id': place_id,
            'api_key': serpapi_key,
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"SerpAPI yelp_reviews error {resp.status_code}: {resp.text}")
    return resp.json().get('reviews', [])


def main():
    parser = argparse.ArgumentParser(description='Yelp VOC Extraction')
    parser.add_argument('--run_id', required=True, help='Run UUID to process')
    args = parser.parse_args()

    load_env()

    serpapi_key = os.environ.get('SERPAPI_API_KEY', '')
    supabase_url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    secret_key = os.environ.get('SUPABASE_SECRET_KEY', '')

    for name, val in [
        ('SERPAPI_API_KEY', serpapi_key),
        ('SUPABASE_URL', supabase_url),
        ('SUPABASE_SECRET_KEY', secret_key),
    ]:
        if not val:
            print(f"ERROR: {name} not set", file=sys.stderr)
            sys.exit(1)

    run_id = args.run_id
    phrase = get_discovery_phrase(supabase_url, secret_key, run_id)

    businesses_saved = 0
    reviews_saved = 0
    voc_saved = 0
    failed = 0

    try:
        results = search_yelp(serpapi_key, phrase)
    except Exception as e:
        print(f"ERROR: Yelp search failed: {e}", file=sys.stderr)
        sys.exit(1)

    for result in results:
        place_id = result.get('place_id') or result.get('biz_id') or ''
        if not place_id:
            continue

        title = result.get('title', '')
        address = result.get('address', '')
        if isinstance(address, dict):
            address = ' '.join(str(v) for v in address.values() if v)

        try:
            yelp_business_id = supabase_insert(supabase_url, secret_key, 'yelp_businesses', {
                'run_id': run_id,
                'discovery_phrase': phrase,
                'business_id': place_id,
                'title': title,
                'rating': result.get('rating'),
                'reviews_count': result.get('reviews'),
                'address': address,
                'thumbnail': result.get('thumbnail'),
                'position': result.get('position'),
            }, return_id=True)
            businesses_saved += 1
        except Exception as e:
            print(f"WARNING: business insert failed for '{title}': {e}", file=sys.stderr)
            failed += 1
            continue

        try:
            review_list = fetch_reviews(serpapi_key, place_id)
        except Exception as e:
            print(f"WARNING: reviews fetch failed for '{title}': {e}", file=sys.stderr)
            failed += 1
            continue

        for review in review_list:
            comment = review.get('comment', {})
            snippet = comment.get('text') if isinstance(comment, dict) else str(comment or '')
            snippet = snippet or review.get('snippet') or review.get('body') or ''
            if not snippet:
                continue

            try:
                user = review.get('user', {})
                reviewer_name = user.get('name') if isinstance(user, dict) else str(user or '')
                feedback = review.get('feedback', {})
                useful = feedback.get('useful') if isinstance(feedback, dict) else None

                review_id = supabase_insert(supabase_url, secret_key, 'yelp_reviews', {
                    'yelp_business_id': yelp_business_id,
                    'run_id': run_id,
                    'reviewer_name': reviewer_name,
                    'rating': review.get('rating'),
                    'snippet': snippet,
                    'useful_votes': useful,
                    'review_date': review.get('date'),
                }, return_id=True)
                reviews_saved += 1

                supabase_insert(supabase_url, secret_key, 'voc_content', {
                    'run_id': run_id,
                    'body': snippet,
                    'content_type': 'review',
                    'source': 'yelp',
                    'title': title,
                    'star_rating': review.get('rating'),
                    'yelp_review_id': review_id,
                })
                voc_saved += 1
            except Exception as e:
                print(f"WARNING: review insert failed for '{title}': {e}", file=sys.stderr)
                failed += 1

    print(
        f"STATS:run_id={run_id},businesses={businesses_saved},"
        f"reviews={reviews_saved},voc_saved={voc_saved},failed={failed}"
    )


if __name__ == '__main__':
    main()
