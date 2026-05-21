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


from url_extract import fetch_firecrawl


def test_fetch_firecrawl_returns_markdown():
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {'data': {'markdown': 'Hello world content here and more text. ' * 5}}

    with patch('url_extract.requests.post', return_value=mock_resp):
        result = fetch_firecrawl('fake-key', 'https://example.com')

    assert result == 'Hello world content here and more text. ' * 5


def test_fetch_firecrawl_raises_on_http_error():
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 403
    mock_resp.text = 'Forbidden'

    with patch('url_extract.requests.post', return_value=mock_resp):
        try:
            fetch_firecrawl('fake-key', 'https://example.com')
            assert False, 'Should have raised'
        except RuntimeError as e:
            assert '403' in str(e)


def test_fetch_firecrawl_raises_on_empty_response():
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {'data': {'markdown': 'short'}}

    with patch('url_extract.requests.post', return_value=mock_resp):
        try:
            fetch_firecrawl('fake-key', 'https://example.com')
            assert False, 'Should have raised'
        except RuntimeError as e:
            assert 'short' in str(e).lower() or 'empty' in str(e).lower()


from url_extract import extract_voc, strip_fences


def _make_anthropic_response(text, stop_reason='end_turn'):
    msg = MagicMock()
    msg.stop_reason = stop_reason
    block = MagicMock()
    block.type = 'text'
    block.text = text
    msg.content = [block]
    return msg


def test_extract_voc_returns_items():
    payload = json.dumps([
        {'content_type': 'original_post', 'body': 'Main post text', 'author': 'alice', 'position': 1, 'parent_position': None},
        {'content_type': 'comment', 'body': 'A reply here', 'author': 'bob', 'position': 2, 'parent_position': 1},
    ])
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_anthropic_response(payload)

    items, truncated = extract_voc(mock_client, 'Some markdown content', 'Page Title')

    assert len(items) == 2
    assert items[0]['content_type'] == 'original_post'
    assert items[1]['parent_position'] == 1
    assert truncated is False


def test_extract_voc_detects_truncation():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_anthropic_response('[]', stop_reason='max_tokens')

    _, truncated = extract_voc(mock_client, 'content', 'title')
    assert truncated is True


def test_extract_voc_strips_fences():
    payload = '```json\n[{"content_type":"comment","body":"hi","author":null,"position":1,"parent_position":null}]\n```'
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_anthropic_response(payload)

    items, _ = extract_voc(mock_client, 'content', 'title')
    assert len(items) == 1
    assert items[0]['body'] == 'hi'


def test_extract_voc_raises_on_bad_json():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_anthropic_response('not json at all')

    try:
        extract_voc(mock_client, 'content', 'title')
        assert False, 'Should have raised'
    except RuntimeError as e:
        assert 'parse' in str(e).lower() or 'json' in str(e).lower()


def test_strip_fences_plain_json():
    assert strip_fences('[1,2,3]') == '[1,2,3]'


def test_strip_fences_with_markdown():
    assert strip_fences('```json\n[1,2,3]\n```') == '[1,2,3]'


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
