import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPT = str(Path(__file__).parent / 'url_extract.py')


def test_help_exits_zero():
    result = subprocess.run(
        [sys.executable, SCRIPT, '--help'],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert '--run_id' in result.stdout


def test_missing_run_id_exits_nonzero():
    result = subprocess.run(
        [sys.executable, SCRIPT],
        capture_output=True, text=True
    )
    assert result.returncode != 0


from url_extract import deduplicate_by_url


def test_deduplicate_no_dupes():
    rows = [
        {'id': 'aaa', 'url': 'https://example.com/1', 'title': 'Post 1'},
        {'id': 'bbb', 'url': 'https://example.com/2', 'title': 'Post 2'},
    ]
    result = deduplicate_by_url(rows)
    assert len(result) == 2
    assert result['https://example.com/1']['serp_result_ids'] == ['aaa']
    assert result['https://example.com/2']['serp_result_ids'] == ['bbb']


def test_deduplicate_with_dupes():
    rows = [
        {'id': 'aaa', 'url': 'https://example.com/1', 'title': 'Post 1'},
        {'id': 'bbb', 'url': 'https://example.com/1', 'title': 'Post 1'},
        {'id': 'ccc', 'url': 'https://example.com/2', 'title': 'Post 2'},
    ]
    result = deduplicate_by_url(rows)
    assert len(result) == 2
    assert sorted(result['https://example.com/1']['serp_result_ids']) == ['aaa', 'bbb']
    assert result['https://example.com/2']['serp_result_ids'] == ['ccc']


def test_deduplicate_title_from_first_row():
    rows = [
        {'id': 'aaa', 'url': 'https://example.com/1', 'title': 'First Title'},
        {'id': 'bbb', 'url': 'https://example.com/1', 'title': 'Second Title'},
    ]
    result = deduplicate_by_url(rows)
    assert result['https://example.com/1']['title'] == 'First Title'


def test_deduplicate_null_title():
    rows = [{'id': 'aaa', 'url': 'https://example.com/1', 'title': None}]
    result = deduplicate_by_url(rows)
    assert result['https://example.com/1']['title'] == ''


from url_extract import run_summary


def test_run_summary_output(capsys):
    rows = [
        {'id': 'aaa', 'url': 'https://a.com', 'title': 'A'},
        {'id': 'bbb', 'url': 'https://b.com', 'title': 'B'},
        {'id': 'ccc', 'url': 'https://a.com', 'title': 'A'},  # duplicate
    ]
    with patch('url_extract.fetch_serp_results', return_value=rows):
        run_summary('https://fake.supabase.co', 'fake-key', 'run-uuid-123')

    captured = capsys.readouterr()
    assert 'SUMMARY:run_id=run-uuid-123,total=3,unique=2,dupes=1' in captured.out


def test_summary_only_flag_accepted():
    # With no env vars set, should error on SUPABASE_URL — not on unknown flag
    result = subprocess.run(
        [sys.executable, SCRIPT, '--run_id', 'test-uuid', '--summary-only'],
        capture_output=True, text=True,
        env={'PATH': __import__('os').environ.get('PATH', '')}  # strip env vars
    )
    # Should fail on missing SUPABASE_URL, not on unrecognized --summary-only
    assert 'SUPABASE_URL' in result.stderr or result.returncode != 0
    assert 'unrecognized' not in result.stderr
