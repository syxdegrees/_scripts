import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, r'C:\Users\jeshj\Desktop\Coding\_scripts\customer-discovery')
import customer_discovery_google_play_voc_extraction as script


def make_books_response():
    return {
        'organic_results': [
            {
                'product_id': 'book123',
                'title': 'Test Book',
                'authors': 'Jane Doe',
                'description': 'A test book about weight loss.',
                'rating': 4.2,
                'reviews': 120,
                'price': '$9.99',
                'thumbnail': 'https://example.com/thumb.jpg',
                'position': 1,
            }
        ]
    }


def make_apps_response():
    return {
        'organic_results': [
            {
                'product_id': 'app456',
                'title': 'Test App',
                'description': 'A weight loss app.',
                'rating': 3.8,
                'reviews': 500,
                'price': 'Free',
                'thumbnail': 'https://example.com/app.jpg',
                'position': 1,
            }
        ]
    }


def make_reviews_response(rating):
    return {
        'reviews': [
            {
                'title': f'Reviewer{rating}',
                'rating': rating,
                'snippet': f'This is a {rating}-star review.',
                'likes': rating * 2,
                'date': '2026-01-01',
            }
        ]
    }


def make_supabase_response(id_val):
    mock = MagicMock()
    mock.ok = True
    mock.json.return_value = [{'id': id_val}]
    return mock


@patch('customer_discovery_google_play_voc_extraction.requests.get')
@patch('customer_discovery_google_play_voc_extraction.requests.post')
def test_main_produces_stats_line(mock_post, mock_get, capsys):
    """main() runs full pipeline and prints a STATS line to stdout."""
    run_id = 'run-uuid-1234'
    post_id = [0]

    def get_side_effect(url, **kwargs):
        mock = MagicMock()
        mock.ok = True
        params = kwargs.get('params', {})
        if '/runs' in url:
            mock.json.return_value = [{'discovery_phrase': 'weight loss'}]
            return mock
        engine = params.get('engine', '')
        if engine == 'google_play_books':
            mock.json.return_value = make_books_response()
        elif engine == 'google_play':
            mock.json.return_value = make_apps_response()
        elif engine == 'google_play_product_reviews':
            mock.json.return_value = make_reviews_response(int(params.get('rating', 1)))
        else:
            mock.json.return_value = {}
        return mock

    def post_side_effect(url, **kwargs):
        post_id[0] += 1
        return make_supabase_response(f'id-{post_id[0]}')

    mock_get.side_effect = get_side_effect
    mock_post.side_effect = post_side_effect

    with patch('sys.argv', ['script', '--run_id', run_id]):
        with patch.dict('os.environ', {
            'SERPAPI_API_KEY': 'test-serp-key',
            'SUPABASE_URL': 'https://example.supabase.co',
            'SUPABASE_SECRET_KEY': 'test-secret',
        }):
            script.main()

    captured = capsys.readouterr()
    assert 'STATS:' in captured.out
    stats_line = next(l for l in captured.out.splitlines() if l.startswith('STATS:'))
    parts = dict(kv.split('=') for kv in stats_line[len('STATS:'):].split(','))
    assert parts['run_id'] == run_id
    assert int(parts['books']) == 2    # 1 book + 1 app
    assert int(parts['reviews']) > 0
    assert int(parts['voc_saved']) > 0
    assert int(parts['failed']) == 0


@patch('customer_discovery_google_play_voc_extraction.requests.get')
@patch('customer_discovery_google_play_voc_extraction.requests.post')
def test_engine_failure_is_warned_not_fatal(mock_post, mock_get, capsys):
    """If google_play_books engine fails, script warns and continues to google_play."""
    post_id = [0]

    def get_side_effect(url, **kwargs):
        mock = MagicMock()
        mock.ok = True
        params = kwargs.get('params', {})
        if '/runs' in url:
            mock.json.return_value = [{'discovery_phrase': 'weight loss'}]
            return mock
        engine = params.get('engine', '')
        if engine == 'google_play_books':
            mock.ok = False
            mock.status_code = 500
            mock.text = 'Server error'
        elif engine == 'google_play':
            mock.json.return_value = make_apps_response()
        elif engine == 'google_play_product_reviews':
            mock.json.return_value = make_reviews_response(int(params.get('rating', 1)))
        return mock

    def post_side_effect(url, **kwargs):
        post_id[0] += 1
        return make_supabase_response(f'id-{post_id[0]}')

    mock_get.side_effect = get_side_effect
    mock_post.side_effect = post_side_effect

    with patch('sys.argv', ['script', '--run_id', 'run-uuid-5678']):
        with patch.dict('os.environ', {
            'SERPAPI_API_KEY': 'test-serp-key',
            'SUPABASE_URL': 'https://example.supabase.co',
            'SUPABASE_SECRET_KEY': 'test-secret',
        }):
            script.main()

    captured = capsys.readouterr()
    assert 'WARNING' in captured.err
    assert 'STATS:' in captured.out
    stats_line = next(l for l in captured.out.splitlines() if l.startswith('STATS:'))
    parts = dict(kv.split('=') for kv in stats_line[len('STATS:'):].split(','))
    assert int(parts['books']) == 1    # only app, books engine failed
