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


from url_extract import save_voc_content, VOC_TABLE, JUNCTION_TABLE


def test_save_voc_content_inserts_in_position_order():
    items = [
        {'content_type': 'original_post', 'body': 'Post body', 'author': 'alice', 'position': 1, 'parent_position': None},
        {'content_type': 'comment', 'body': 'Comment body', 'author': 'bob', 'position': 2, 'parent_position': 1},
    ]
    inserted_ids = ['uuid-1', 'uuid-2']
    call_count = [0]

    def mock_post(url, headers=None, json=None, timeout=None):
        resp = MagicMock()
        resp.ok = True
        if JUNCTION_TABLE in url:
            resp.json.return_value = []
        elif VOC_TABLE in url:
            idx = call_count[0]
            resp.json.return_value = [{'id': inserted_ids[idx]}]
            call_count[0] += 1
        else:
            resp.json.return_value = []
        return resp

    with patch('url_extract.requests.post', side_effect=mock_post):
        count = save_voc_content(
            'https://fake.supabase.co', 'fake-key',
            'run-uuid', 'https://example.com', 'Page Title',
            items, ['serp-id-1', 'serp-id-2']
        )

    assert count == 2


def test_save_voc_content_sets_parent_id():
    items = [
        {'content_type': 'original_post', 'body': 'Post', 'author': None, 'position': 1, 'parent_position': None},
        {'content_type': 'comment', 'body': 'Reply', 'author': None, 'position': 2, 'parent_position': 1},
    ]
    inserted_payloads = []

    def mock_post(url, headers=None, json=None, timeout=None):
        resp = MagicMock()
        resp.ok = True
        if JUNCTION_TABLE in url:
            resp.json.return_value = []
        elif VOC_TABLE in url and isinstance(json, dict):
            inserted_payloads.append(json)
            idx = len(inserted_payloads) - 1
            resp.json.return_value = [{'id': f'uuid-{idx + 1}'}]
        else:
            resp.json.return_value = []
        return resp

    with patch('url_extract.requests.post', side_effect=mock_post):
        save_voc_content(
            'https://fake.supabase.co', 'fake-key',
            'run-uuid', 'https://example.com', 'Title',
            items, ['serp-id-1']
        )

    assert inserted_payloads[0]['parent_id'] is None
    assert inserted_payloads[1]['parent_id'] == 'uuid-1'


from url_extract import run_extract


def test_run_extract_full_flow(capsys):
    serp_rows = [
        {'id': 'serp-1', 'url': 'https://example.com/post', 'title': 'Test Post'},
        {'id': 'serp-2', 'url': 'https://example.com/post', 'title': 'Test Post'},  # duplicate
    ]
    voc_items = [
        {'content_type': 'original_post', 'body': 'Full post text here', 'author': 'alice', 'position': 1, 'parent_position': None},
        {'content_type': 'comment', 'body': 'A comment here', 'author': 'bob', 'position': 2, 'parent_position': 1},
    ]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_anthropic_response(json.dumps(voc_items))

    save_call_count = [0]

    def mock_post(url, headers=None, json=None, timeout=None):
        resp = MagicMock()
        resp.ok = True
        if JUNCTION_TABLE in url:
            resp.json.return_value = []
        elif VOC_TABLE in url and isinstance(json, dict):
            idx = save_call_count[0]
            resp.json.return_value = [{'id': f'voc-{idx}'}]
            save_call_count[0] += 1
        else:
            resp.json.return_value = []
        return resp

    with patch('url_extract.fetch_serp_results', return_value=serp_rows), \
         patch('url_extract.fetch_firecrawl', return_value='Some markdown content for extraction'), \
         patch('url_extract.anthropic') as mock_anthropic_module, \
         patch('url_extract.requests.post', side_effect=mock_post):

        mock_anthropic_module.Anthropic.return_value = mock_client
        run_extract('https://fake.supabase.co', 'fake-key', 'fc-key', 'ant-key', 'run-uuid')

    captured = capsys.readouterr()
    assert 'Extracting [1/1]' in captured.out
    assert 'STATS:run_id=run-uuid' in captured.out
    assert 'urls_processed=1' in captured.out
    assert 'items_saved=2' in captured.out
    assert 'failed=0' in captured.out


def test_run_extract_handles_firecrawl_failure(capsys):
    serp_rows = [{'id': 'serp-1', 'url': 'https://bad-url.com', 'title': 'Bad'}]

    with patch('url_extract.fetch_serp_results', return_value=serp_rows), \
         patch('url_extract.fetch_firecrawl', side_effect=RuntimeError('blocked')), \
         patch('url_extract.anthropic') as mock_anthropic_module:

        mock_anthropic_module.Anthropic.return_value = MagicMock()
        run_extract('https://fake.supabase.co', 'fake-key', 'fc-key', 'ant-key', 'run-uuid')

    captured = capsys.readouterr()
    assert 'WARNING' in captured.err
    assert 'failed=1' in captured.out
    assert 'urls_processed=0' in captured.out


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
