#!/usr/bin/env python3
"""
customer_discovery_news_voc_extraction.py
Queries Google News Light + Bing News APIs for a run's discovery phrase,
saves raw article metadata to news_results, and queues article URLs in
news_urls for scraping by the URL VOC extraction stage.
Deduplicates against serp_urls to avoid double-scraping.

Dependencies: pip install requests
Usage: python customer_discovery_news_voc_extraction.py --run_id <uuid>
"""

import argparse
import os
import sys
import requests
from pathlib import Path

SERPAPI_URL = "https://serpapi.com/search"
MAX_PAGES = 2


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


def _headers(secret_key):
    return {'apikey': secret_key, 'Authorization': f'Bearer {secret_key}'}


def get_discovery_phrase(supabase_url, secret_key, run_id):
    resp = requests.get(
        f"{supabase_url}/rest/v1/runs",
        headers=_headers(secret_key),
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


def fetch_existing_serp_urls(supabase_url, secret_key, run_id):
    """Return set of URLs already queued in serp_urls for this run."""
    resp = requests.get(
        f"{supabase_url}/rest/v1/serp_urls",
        headers=_headers(secret_key),
        params={'run_id': f'eq.{run_id}', 'select': 'url'},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"serp_urls query failed: {resp.status_code} {resp.text}")
    return {row['url'] for row in resp.json()}


def _default_insert(supabase_url, secret_key, table, row, return_id=False):
    headers = {
        **_headers(secret_key),
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


def process_articles(supabase_url, secret_key, run_id, phrase, articles, engine,
                     existing_serp_urls, insert_fn=None):
    """Save each article to news_results and queue its URL in news_urls.

    Skips news_urls insert if the URL already exists in serp_urls.
    insert_fn is injectable for testing; defaults to _default_insert.
    Returns (articles_saved, urls_queued, failed).
    """
    if insert_fn is None:
        insert_fn = _default_insert

    articles_saved = urls_queued = failed = 0

    for article in articles:
        try:
            news_result_id = insert_fn(supabase_url, secret_key, 'news_results', {
                'run_id': run_id,
                'search_query': phrase,
                'engine': engine,
                'position': article.get('position'),
                'title': article.get('title'),
                'link': article.get('link'),
                'snippet': article.get('snippet'),
                'source': article.get('source'),
                'pub_date': article.get('date'),
                'thumbnail_url': article.get('thumbnail'),
            }, return_id=True)
            articles_saved += 1

            article_url = article.get('link') or ''
            if article_url and article_url not in existing_serp_urls:
                insert_fn(supabase_url, secret_key, 'news_urls', {
                    'run_id': run_id,
                    'news_result_id': news_result_id,
                    'url': article_url,
                    'title': article.get('title'),
                    'source': engine,
                })
                urls_queued += 1

        except Exception as e:
            print(f"WARNING: Article '{article.get('title', '')}' failed: {e}", file=sys.stderr)
            failed += 1

    return articles_saved, urls_queued, failed


def fetch_google_news(phrase, api_key, page):
    resp = requests.get(
        SERPAPI_URL,
        params={'engine': 'google_news_light', 'q': phrase, 'api_key': api_key, 'start': page * 10},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Google News error: {resp.status_code} {resp.text}")
    return resp.json().get('news_results', [])


def fetch_bing_news(phrase, api_key, page):
    resp = requests.get(
        SERPAPI_URL,
        params={'engine': 'bing_news', 'q': phrase, 'api_key': api_key, 'first': 1 + (page * 10)},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Bing News error: {resp.status_code} {resp.text}")
    return resp.json().get('organic_results', [])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run_id', required=True)
    args = parser.parse_args()

    load_env()
    supabase_url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    secret_key = os.environ.get('SUPABASE_SECRET_KEY', '')
    serpapi_key = os.environ.get('SERPAPI_API_KEY', '')

    for name, val in [('SUPABASE_URL', supabase_url), ('SUPABASE_SECRET_KEY', secret_key),
                      ('SERPAPI_API_KEY', serpapi_key)]:
        if not val:
            print(f"ERROR: {name} not set", file=sys.stderr)
            sys.exit(1)

    run_id = args.run_id
    phrase = get_discovery_phrase(supabase_url, secret_key, run_id)
    existing_serp_urls = fetch_existing_serp_urls(supabase_url, secret_key, run_id)

    total_articles = total_urls_saved = total_failed = 0

    for page in range(MAX_PAGES):
        try:
            articles = fetch_google_news(phrase, serpapi_key, page)
            a, u, f = process_articles(supabase_url, secret_key, run_id, phrase,
                                       articles, 'google_news_light', existing_serp_urls)
            total_articles += a; total_urls_saved += u; total_failed += f
        except Exception as e:
            print(f"WARNING: Google News page {page + 1} failed: {e}", file=sys.stderr)
            total_failed += 1

    for page in range(MAX_PAGES):
        try:
            articles = fetch_bing_news(phrase, serpapi_key, page)
            a, u, f = process_articles(supabase_url, secret_key, run_id, phrase,
                                       articles, 'bing_news', existing_serp_urls)
            total_articles += a; total_urls_saved += u; total_failed += f
        except Exception as e:
            print(f"WARNING: Bing News page {page + 1} failed: {e}", file=sys.stderr)
            total_failed += 1

    print(f"STATS:run_id={run_id},articles={total_articles},urls_saved={total_urls_saved},failed={total_failed}")


if __name__ == '__main__':
    main()
