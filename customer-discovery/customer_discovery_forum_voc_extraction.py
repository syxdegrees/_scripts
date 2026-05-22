#!/usr/bin/env python3
"""
customer_discovery_voc_forum_extraction.py
Queries Google Forums API for a run's discovery phrase, saves raw thread
data to forum_results/forum_answers, and normalized VoC to voc_content.

Dependencies: pip install requests
Usage: python customer_discovery_voc_forum_extraction.py --run_id <uuid>
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


def extract_platform(link):
    if not link:
        return None
    known = ['reddit.com', 'quora.com', 'stackoverflow.com', 'stackexchange.com',
             'hackernews.com', 'ycombinator.com', 'forums.', 'community.']
    for k in known:
        if k in link:
            return k.rstrip('.')
    parts = link.split('/')
    return parts[2] if len(parts) > 2 else None


def fetch_page(phrase, api_key, page):
    resp = requests.get(
        SERPAPI_URL,
        params={'engine': 'google_forums', 'q': phrase, 'api_key': api_key, 'start': page * 10},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"SerpAPI error: {resp.status_code} {resp.text}")
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

    threads_saved = answers_saved = voc_saved = failed = 0

    for page in range(MAX_PAGES):
        try:
            results = fetch_page(phrase, serpapi_key, page)
        except Exception as e:
            print(f"WARNING: Page {page + 1} fetch failed: {e}", file=sys.stderr)
            failed += 1
            continue

        for result in results:
            try:
                forum_result_id = supabase_insert(supabase_url, secret_key, 'forum_results', {
                    'run_id': run_id,
                    'search_query': phrase,
                    'position': result.get('position'),
                    'title': result.get('title'),
                    'link': result.get('link'),
                    'redirect_link': result.get('redirect_link'),
                    'displayed_link': result.get('displayed_link'),
                    'displayed_meta': result.get('displayed_meta'),
                    'snippet': result.get('snippet'),
                    'post_date': result.get('date'),
                    'source_platform': extract_platform(result.get('link')),
                    'source_name': result.get('source'),
                    'thumbnail_url': result.get('thumbnail'),
                }, return_id=True)
                threads_saved += 1

                thread_voc_id = supabase_insert(supabase_url, secret_key, 'voc_content', {
                    'run_id': run_id,
                    'body': result.get('snippet') or '',
                    'content_type': 'thread',
                    'source': 'forum',
                    'source_url': result.get('link'),
                    'title': result.get('title'),
                    'forum_result_id': forum_result_id,
                }, return_id=True)
                voc_saved += 1

                for answer in result.get('answers', []):
                    try:
                        supabase_insert(supabase_url, secret_key, 'forum_answers', {
                            'forum_result_id': forum_result_id,
                            'run_id': run_id,
                            'link': answer.get('link'),
                            'answer_text': answer.get('answer') or '',
                            'is_top_answer': bool(answer.get('top_answer')),
                            'votes': answer.get('votes'),
                        })
                        answers_saved += 1

                        supabase_insert(supabase_url, secret_key, 'voc_content', {
                            'run_id': run_id,
                            'body': answer.get('answer') or '',
                            'content_type': 'answer',
                            'source': 'forum',
                            'source_url': answer.get('link'),
                            'upvotes': answer.get('votes'),
                            'is_top': bool(answer.get('top_answer')),
                            'forum_result_id': forum_result_id,
                            'parent_id': thread_voc_id,
                        })
                        voc_saved += 1
                    except Exception as e:
                        print(f"WARNING: Answer save failed: {e}", file=sys.stderr)
                        failed += 1

            except Exception as e:
                print(f"WARNING: Result '{result.get('title', '')}' failed: {e}", file=sys.stderr)
                failed += 1

    print(f"STATS:run_id={run_id},threads={threads_saved},answers={answers_saved},voc_saved={voc_saved},failed={failed}")


if __name__ == '__main__':
    main()
