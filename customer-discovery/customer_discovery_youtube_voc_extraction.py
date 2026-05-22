#!/usr/bin/env python3
"""
customer_discovery_youtube_voc_extraction.py
Searches YouTube for a run's discovery phrase, fetches video comments,
and saves to youtube_videos, youtube_comments, and voc_content.

Dependencies: pip install requests

Usage:
    python customer_discovery_youtube_voc_extraction.py --run_id <uuid>
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


def search_youtube(serpapi_key, phrase):
    resp = requests.get(
        SERPAPI_URL,
        params={'engine': 'youtube', 'search_query': phrase, 'api_key': serpapi_key},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"SerpAPI youtube error {resp.status_code}: {resp.text}")
    return resp.json().get('video_results', [])


def fetch_comments(serpapi_key, video_id):
    resp = requests.get(
        SERPAPI_URL,
        params={
            'engine': 'youtube_video',
            'v': video_id,
            'api_key': serpapi_key,
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"SerpAPI youtube_video error {resp.status_code}: {resp.text}")
    return resp.json().get('comments', [])


def main():
    parser = argparse.ArgumentParser(description='YouTube VOC Extraction')
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

    videos_saved = 0
    comments_saved = 0
    voc_saved = 0
    failed = 0

    try:
        results = search_youtube(serpapi_key, phrase)
    except Exception as e:
        print(f"ERROR: YouTube search failed: {e}", file=sys.stderr)
        sys.exit(1)

    for result in results:
        video_id = result.get('video_id') or result.get('id') or ''
        if not video_id:
            link = result.get('link', '')
            if 'v=' in link:
                video_id = link.split('v=')[-1].split('&')[0]
        if not video_id:
            continue

        title = result.get('title', '')
        channel = result.get('channel', {})
        channel_name = channel.get('name') if isinstance(channel, dict) else str(channel or '')
        thumbnail = result.get('thumbnail', {})
        thumbnail_url = thumbnail.get('static') if isinstance(thumbnail, dict) else thumbnail

        try:
            yt_video_id = supabase_insert(supabase_url, secret_key, 'youtube_videos', {
                'run_id': run_id,
                'discovery_phrase': phrase,
                'video_id': video_id,
                'title': title,
                'channel': channel_name,
                'view_count': str(result.get('views', '') or ''),
                'publish_date': result.get('published_date'),
                'thumbnail': thumbnail_url,
                'position': result.get('position'),
            }, return_id=True)
            videos_saved += 1
        except Exception as e:
            print(f"WARNING: video insert failed for '{title}': {e}", file=sys.stderr)
            failed += 1
            continue

        try:
            comment_list = fetch_comments(serpapi_key, video_id)
        except Exception as e:
            print(f"WARNING: comments fetch failed for '{title}': {e}", file=sys.stderr)
            failed += 1
            continue

        for comment in comment_list:
            snippet = comment.get('content') or comment.get('text') or comment.get('snippet') or ''
            if not snippet:
                continue

            try:
                comment_id = supabase_insert(supabase_url, secret_key, 'youtube_comments', {
                    'youtube_video_id': yt_video_id,
                    'run_id': run_id,
                    'author': comment.get('author'),
                    'snippet': snippet,
                    'likes': comment.get('likes'),
                    'published_at': comment.get('published_date') or comment.get('published_at'),
                }, return_id=True)
                comments_saved += 1

                supabase_insert(supabase_url, secret_key, 'voc_content', {
                    'run_id': run_id,
                    'body': snippet,
                    'content_type': 'comment',
                    'source': 'youtube',
                    'title': title,
                    'youtube_comment_id': comment_id,
                })
                voc_saved += 1
            except Exception as e:
                print(f"WARNING: comment insert failed for '{title}': {e}", file=sys.stderr)
                failed += 1

    print(
        f"STATS:run_id={run_id},videos={videos_saved},"
        f"comments={comments_saved},voc_saved={voc_saved},failed={failed}"
    )


if __name__ == '__main__':
    main()
