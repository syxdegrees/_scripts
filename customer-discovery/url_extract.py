#!/usr/bin/env python3
"""
url_extract.py
VOC URL content extraction — fetches URLs from serp_results for a run_id,
scrapes via Firecrawl, extracts structured VOC via Claude, saves to Supabase.

Dependencies: pip install requests anthropic

Usage:
    python url_extract.py --run_id <uuid>
    python url_extract.py --run_id <uuid> --summary-only
"""

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic
import requests

FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
VOC_TABLE = "voc_content"
JUNCTION_TABLE = "voc_content_serp_results"

EXTRACT_SYSTEM = """You extract user-generated content from web pages for Voice of Customer research.

Return ONLY a JSON array. No markdown, no explanation, no wrapper object.

Each item:
{
  "content_type": "original_post" | "comment" | "review" | "reply",
  "body": string,
  "author": string | null,
  "position": number,
  "parent_position": number | null
}

Rules:
- position 1 is always the original post or first root item
- comments directly under the original post: parent_position = 1
- replies to a comment: parent_position = that comment's position
- Include ALL content written by real users — posts, comments, reviews, replies
- Exclude: article body, navigation, ads, headers, footers, author bios
- NEVER truncate body text -- include the complete text of every item
- If no user content exists, return []"""


def load_env():
    """Load .env from script folder first, then cwd, then rely on environment."""
    for env_path in [Path(__file__).parent / '.env', Path.cwd() / '.env']:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, _, value = line.partition('=')
                        os.environ.setdefault(key.strip(), value.strip())
            break


def main():
    parser = argparse.ArgumentParser(description='VOC URL Content Extraction')
    parser.add_argument('--run_id', required=True, help='Run UUID to process')
    parser.add_argument('--summary-only', action='store_true',
                        help='Print dedup summary and exit without extracting')
    args = parser.parse_args()

    load_env()

    supabase_url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    supabase_key = os.environ.get('SUPABASE_SECRET_KEY', '')
    firecrawl_key = os.environ.get('FIRECRAWL_API_KEY', '')
    anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')

    if not supabase_url:
        print("ERROR: SUPABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    if not supabase_key:
        print("ERROR: SUPABASE_SECRET_KEY not set", file=sys.stderr)
        sys.exit(1)

    if args.summary_only:
        run_summary(supabase_url, supabase_key, args.run_id)
        return

    if not firecrawl_key:
        print("ERROR: FIRECRAWL_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    if not anthropic_key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    run_extract(supabase_url, supabase_key, firecrawl_key, anthropic_key, args.run_id)


def _supabase_headers(secret_key):
    return {
        'apikey': secret_key,
        'Authorization': f'Bearer {secret_key}',
        'Content-Type': 'application/json',
    }


def fetch_serp_results(supabase_url, secret_key, run_id):
    """Return list of {id, url, title} dicts for all serp_results with this run_id."""
    url = f"{supabase_url}/rest/v1/serp_results"
    params = {'run_id': f'eq.{run_id}', 'select': 'id,url,title'}
    resp = requests.get(url, headers=_supabase_headers(secret_key), params=params, timeout=30)
    if not resp.ok:
        print(f"ERROR: Supabase query failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.json()


def deduplicate_by_url(rows):
    """Group rows by URL. Returns {url: {title, serp_result_ids: [...]}}."""
    grouped = {}
    for row in rows:
        url = row['url']
        if url not in grouped:
            grouped[url] = {'title': row.get('title') or '', 'serp_result_ids': []}
        grouped[url]['serp_result_ids'].append(row['id'])
    return grouped


def run_summary(supabase_url, supabase_key, run_id):
    pass  # implemented in Task 4


def run_extract(supabase_url, supabase_key, firecrawl_key, anthropic_key, run_id):
    pass  # implemented in Task 8


if __name__ == '__main__':
    main()
