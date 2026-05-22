#!/usr/bin/env python3
"""
customer_discovery_voc_news_extraction.py
Queries Google News Light + Bing News APIs for a run's discovery phrase,
saves raw articles to news_results and normalized VoC to voc_content.

Dependencies: pip install requests
Usage: python customer_discovery_voc_news_extraction.py --run_id <uuid>
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


def process_articles(supabase_url, secret_key, run_id, phrase, articles, engine):
    saved = voc = failed = 0
    for article in articles:
        try:
            news_result_id = supabase_insert(supabase_url, secret_key, 'news_results', {
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
            saved += 1

            supabase_insert(supabase_url, secret_key, 'voc_content', {
                'run_id': run_id,
                'body': article.get('snippet') or '',
                'content_type': 'article',
                'source': 'news',
                'source_url': article.get('link'),
                'title': article.get('title'),
                'news_result_id': news_result_id,
            })
            voc += 1
        except Exception as e:
            print(f"WARNING: Article '{article.get('title', '')}' failed: {e}", file=sys.stderr)
            failed += 1
    return saved, voc, failed


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

    total_articles = total_voc = total_failed = 0

    for page in range(MAX_PAGES):
        try:
            articles = fetch_google_news(phrase, serpapi_key, page)
            a, v, f = process_articles(supabase_url, secret_key, run_id, phrase, articles, 'google_news_light')
            total_articles += a; total_voc += v; total_failed += f
        except Exception as e:
            print(f"WARNING: Google News page {page + 1} failed: {e}", file=sys.stderr)
            total_failed += 1

    for page in range(MAX_PAGES):
        try:
            articles = fetch_bing_news(phrase, serpapi_key, page)
            a, v, f = process_articles(supabase_url, secret_key, run_id, phrase, articles, 'bing_news')
            total_articles += a; total_voc += v; total_failed += f
        except Exception as e:
            print(f"WARNING: Bing News page {page + 1} failed: {e}", file=sys.stderr)
            total_failed += 1

    print(f"STATS:run_id={run_id},articles={total_articles},voc_saved={total_voc},failed={total_failed}")


if __name__ == '__main__':
    main()
