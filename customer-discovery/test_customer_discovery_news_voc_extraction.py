import sys
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

SCRIPT = str(Path(__file__).parent / 'customer_discovery_news_voc_extraction.py')

from customer_discovery_news_voc_extraction import process_articles


def test_help_exits_zero():
    result = subprocess.run(
        [sys.executable, SCRIPT, '--help'],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert '--run_id' in result.stdout


def test_process_articles_skips_duplicate_serp_url():
    """URLs already in serp_urls must not be inserted into news_urls."""
    existing = {'https://example.com/article'}
    articles = [{'link': 'https://example.com/article', 'title': 'Test', 'position': 1}]

    insert_calls = []

    def fake_insert(surl, key, table, row, return_id=False):
        insert_calls.append(table)
        return 'fake-uuid'

    saved, urls_queued, failed = process_articles(
        'http://supabase', 'key', 'run-1', 'test phrase',
        articles, 'google_news_light', existing,
        insert_fn=fake_insert,
    )

    assert saved == 1           # news_results insert happened
    assert urls_queued == 0     # news_urls insert skipped
    assert failed == 0
    assert 'news_urls' not in insert_calls


def test_process_articles_queues_new_url():
    """URLs not in serp_urls must be inserted into news_urls."""
    existing = set()
    articles = [{'link': 'https://example.com/new', 'title': 'New Article', 'position': 1}]

    insert_calls = []

    def fake_insert(surl, key, table, row, return_id=False):
        insert_calls.append(table)
        return 'fake-uuid'

    saved, urls_queued, failed = process_articles(
        'http://supabase', 'key', 'run-1', 'test phrase',
        articles, 'google_news_light', existing,
        insert_fn=fake_insert,
    )

    assert saved == 1
    assert urls_queued == 1
    assert failed == 0
    assert insert_calls == ['news_results', 'news_urls']


def test_process_articles_skips_empty_link():
    """Articles with no link must not be inserted into news_urls."""
    existing = set()
    articles = [{'link': None, 'title': 'No Link', 'position': 1}]

    insert_calls = []

    def fake_insert(surl, key, table, row, return_id=False):
        insert_calls.append(table)
        return 'fake-uuid'

    saved, urls_queued, failed = process_articles(
        'http://supabase', 'key', 'run-1', 'test phrase',
        articles, 'google_news_light', existing,
        insert_fn=fake_insert,
    )

    assert urls_queued == 0
    assert 'news_urls' not in insert_calls
