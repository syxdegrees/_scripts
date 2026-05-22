#!/usr/bin/env python3
"""
customer_discovery_walmart_voc_extraction.py
Searches Walmart for a run's discovery phrase, fetches product reviews,
and saves to walmart_products, walmart_reviews, and voc_content.

Dependencies: pip install requests

Usage:
    python customer_discovery_walmart_voc_extraction.py --run_id <uuid>
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


def search_walmart(serpapi_key, phrase):
    resp = requests.get(
        SERPAPI_URL,
        params={'engine': 'walmart', 'query': phrase, 'api_key': serpapi_key},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"SerpAPI walmart error {resp.status_code}: {resp.text}")
    return resp.json().get('organic_results', [])


def fetch_reviews(serpapi_key, product_id):
    resp = requests.get(
        SERPAPI_URL,
        params={
            'engine': 'walmart_product_reviews',
            'product_id': product_id,
            'api_key': serpapi_key,
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"SerpAPI walmart_product_reviews error {resp.status_code}: {resp.text}")
    return resp.json().get('reviews', [])


def main():
    parser = argparse.ArgumentParser(description='Walmart VOC Extraction')
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

    products_saved = 0
    reviews_saved = 0
    voc_saved = 0
    failed = 0

    try:
        results = search_walmart(serpapi_key, phrase)
    except Exception as e:
        print(f"ERROR: Walmart search failed: {e}", file=sys.stderr)
        sys.exit(1)

    for result in results:
        product_id = str(result.get('us_item_id', '') or result.get('product_id', ''))
        if not product_id:
            continue

        title = result.get('title', '')
        price = None
        offer = result.get('primary_offer', {})
        if isinstance(offer, dict):
            price = offer.get('offer_price')

        try:
            walmart_product_id = supabase_insert(supabase_url, secret_key, 'walmart_products', {
                'run_id': run_id,
                'discovery_phrase': phrase,
                'product_id': product_id,
                'title': title,
                'rating': result.get('rating'),
                'reviews_count': result.get('reviews'),
                'price': str(price) if price is not None else None,
                'thumbnail': result.get('thumbnail'),
                'position': result.get('position'),
            }, return_id=True)
            products_saved += 1
        except Exception as e:
            print(f"WARNING: product insert failed for '{title}': {e}", file=sys.stderr)
            failed += 1
            continue

        try:
            review_list = fetch_reviews(serpapi_key, product_id)
        except Exception as e:
            print(f"WARNING: reviews fetch failed for '{title}': {e}", file=sys.stderr)
            failed += 1
            continue

        for review in review_list:
            snippet = review.get('body') or review.get('snippet') or review.get('text') or ''
            if not snippet:
                continue

            try:
                review_id = supabase_insert(supabase_url, secret_key, 'walmart_reviews', {
                    'walmart_product_id': walmart_product_id,
                    'run_id': run_id,
                    'reviewer_name': review.get('reviewer_name') or review.get('author'),
                    'rating': review.get('rating'),
                    'title': review.get('title'),
                    'snippet': snippet,
                    'helpful_votes': review.get('helpful_votes'),
                    'review_date': review.get('date'),
                }, return_id=True)
                reviews_saved += 1

                supabase_insert(supabase_url, secret_key, 'voc_content', {
                    'run_id': run_id,
                    'body': snippet,
                    'content_type': 'review',
                    'source': 'walmart',
                    'title': title,
                    'star_rating': review.get('rating'),
                    'walmart_review_id': review_id,
                })
                voc_saved += 1
            except Exception as e:
                print(f"WARNING: review insert failed for '{title}': {e}", file=sys.stderr)
                failed += 1

    print(
        f"STATS:run_id={run_id},products={products_saved},"
        f"reviews={reviews_saved},voc_saved={voc_saved},failed={failed}"
    )


if __name__ == '__main__':
    main()
