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


def strip_fences(text):
    """Remove markdown code fences if present."""
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1] if '\n' in text else text[3:]
        text = text.rsplit('```', 1)[0].strip()
    return text


def extract_voc(client, markdown, title):
    """Call Claude Haiku to extract structured VOC content.

    Returns (items: list[dict], truncated: bool).
    Raises RuntimeError on JSON parse failure.
    """
    user_msg = (
        f"Page title (hint for identifying the original post): {title}\n\n"
        f"Extract all user-generated content from this page:\n\n{markdown}"
    )
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8192,
        system=EXTRACT_SYSTEM,
        messages=[{'role': 'user', 'content': user_msg}],
    )
    truncated = message.stop_reason == 'max_tokens'
    block = next((b for b in message.content if b.type == 'text'), None)
    text = block.text if block else '[]'

    try:
        items = json.loads(strip_fences(text))
        if not isinstance(items, list):
            raise ValueError("Response is not a JSON array")
    except (json.JSONDecodeError, ValueError) as e:
        raise RuntimeError(f"Failed to parse Claude response as JSON: {e}")

    return items, truncated


def fetch_firecrawl(api_key, url):
    """Fetch URL via Firecrawl REST API. Returns markdown string or raises RuntimeError."""
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    resp = requests.post(
        FIRECRAWL_URL,
        headers=headers,
        json={'url': url, 'formats': ['markdown']},
        timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"Firecrawl error {resp.status_code}: {resp.text}")
    markdown = resp.json().get('data', {}).get('markdown', '')
    if not markdown or len(markdown.strip()) < 100:
        raise RuntimeError(f"Empty or too-short response from Firecrawl for {url}")
    return markdown


def save_voc_content(supabase_url, secret_key, run_id, url, title, items, serp_result_ids):
    """Insert voc_content rows in ascending position order, then junction rows.

    Returns count of voc_content rows inserted.
    Rows MUST be inserted in position order — parent_id lookup depends on it.
    """
    headers_repr = {**_supabase_headers(secret_key), 'Prefer': 'return=representation'}
    headers_min = {**_supabase_headers(secret_key), 'Prefer': 'return=minimal'}

    position_to_id = {}
    items_saved = 0

    for item in sorted(items, key=lambda x: x.get('position', 0)):
        position = item.get('position')
        parent_position = item.get('parent_position')
        parent_id = position_to_id.get(parent_position) if parent_position else None

        row = {
            'run_id': run_id,
            'url': url,
            'title': title or None,
            'content_type': item.get('content_type', 'comment'),
            'parent_id': parent_id,
            'body': item.get('body', ''),
            'author': item.get('author') or None,
            'position': position,
            'source': 'url_extraction',
        }
        resp = requests.post(
            f"{supabase_url}/rest/v1/{VOC_TABLE}",
            headers=headers_repr,
            json=row,
            timeout=30,
        )
        if not resp.ok:
            raise RuntimeError(f"voc_content insert failed: {resp.status_code} {resp.text}")

        inserted_id = resp.json()[0]['id']
        position_to_id[position] = inserted_id
        items_saved += 1

        junction_rows = [
            {'voc_content_id': inserted_id, 'serp_result_id': sid}
            for sid in serp_result_ids
        ]
        j_resp = requests.post(
            f"{supabase_url}/rest/v1/{JUNCTION_TABLE}",
            headers=headers_min,
            json=junction_rows,
            timeout=30,
        )
        if not j_resp.ok:
            print(
                f"WARNING: junction insert failed for item {inserted_id}: "
                f"{j_resp.status_code} {j_resp.text}",
                file=sys.stderr,
            )

    return items_saved


def run_summary(supabase_url, supabase_key, run_id):
    rows = fetch_serp_results(supabase_url, supabase_key, run_id)
    grouped = deduplicate_by_url(rows)
    total = len(rows)
    unique = len(grouped)
    dupes = total - unique
    print(f"SUMMARY:run_id={run_id},total={total},unique={unique},dupes={dupes}")


def run_extract(supabase_url, supabase_key, firecrawl_key, anthropic_key, run_id):
    client = anthropic.Anthropic(api_key=anthropic_key)

    rows = fetch_serp_results(supabase_url, supabase_key, run_id)
    grouped = deduplicate_by_url(rows)

    total = len(grouped)
    urls_processed = 0
    items_saved = 0
    failed = 0
    truncated = 0

    for i, (url, meta) in enumerate(grouped.items(), 1):
        print(f"Extracting [{i}/{total}]: {url}")
        title = meta['title']
        serp_result_ids = meta['serp_result_ids']

        try:
            markdown = fetch_firecrawl(firecrawl_key, url)
        except Exception as e:
            print(f"WARNING: firecrawl failed for '{url}': {e}", file=sys.stderr)
            failed += 1
            continue

        try:
            voc_items, was_truncated = extract_voc(client, markdown, title)
        except Exception as e:
            print(f"WARNING: claude parse failed for '{url}': {e}", file=sys.stderr)
            failed += 1
            continue

        if was_truncated:
            print(f"WARNING: response truncated for '{url}' — saving partial results", file=sys.stderr)
            truncated += 1

        if not voc_items:
            urls_processed += 1
            continue

        try:
            count = save_voc_content(
                supabase_url, supabase_key,
                run_id, url, title, voc_items, serp_result_ids,
            )
            items_saved += count
        except Exception as e:
            print(f"WARNING: save failed for '{url}': {e}", file=sys.stderr)
            failed += 1
            continue

        urls_processed += 1

    print(
        f"STATS:run_id={run_id},urls_processed={urls_processed},"
        f"items_saved={items_saved},failed={failed},truncated={truncated}"
    )


if __name__ == '__main__':
    main()
