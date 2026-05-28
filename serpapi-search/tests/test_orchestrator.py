import json
import sys
import pytest
from unittest.mock import patch, MagicMock
from tests.test_helpers import set_env


def test_missing_search_phrase_exits(monkeypatch):
    set_env(monkeypatch)
    with pytest.raises(SystemExit):
        with patch("sys.argv", ["serpapi_search.py", "--engines", "google_light"]):
            import serpapi_search
            import importlib
            importlib.reload(serpapi_search)
            serpapi_search.main()


def test_missing_api_key_prints_error(monkeypatch, capsys):
    set_env(monkeypatch)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    with patch("shared.db.load_env"), \
         patch("shared.db.get_supabase_config", return_value={"url": "x", "key": "y"}), \
         patch("sys.argv", ["serpapi_search.py",
                            "--search_phrase", "coffee",
                            "--engines", "google_light"]):
        import serpapi_search
        import importlib
        importlib.reload(serpapi_search)
        with pytest.raises(SystemExit):
            serpapi_search.main()
    captured = capsys.readouterr()
    assert "ERROR: SERPAPI_API_KEY" in captured.out


def test_stats_line_printed_on_success(monkeypatch, capsys):
    set_env(monkeypatch)
    fake_result = {"cache_id": "uuid-123", "items_fetched": 1, "items_cached": 0, "items_stored": 1}
    with patch("shared.db.load_env"), \
         patch("shared.db.get_supabase_config", return_value={"url": "x", "key": "y"}), \
         patch("engines.google_light.run", return_value=fake_result):
        with patch("sys.argv", ["serpapi_search.py",
                                "--search_phrase", "coffee",
                                "--engines", "google_light"]):
            import serpapi_search
            import importlib
            importlib.reload(serpapi_search)
            serpapi_search.main()
    captured = capsys.readouterr()
    stats_line = [l for l in captured.out.splitlines() if l.startswith("STATS:")][0]
    data = json.loads(stats_line[7:])
    assert data["search_phrase"] == "coffee"
    assert "google_light" in data["engines"]
    assert data["engines"]["google_light"]["cache_id"] == "uuid-123"


def test_engine_error_does_not_stop_other_engines(monkeypatch, capsys):
    set_env(monkeypatch)
    fake_result = {"cache_id": "uuid-forums", "items_fetched": 1, "items_cached": 0, "items_stored": 1}
    with patch("shared.db.load_env"), \
         patch("shared.db.get_supabase_config", return_value={"url": "x", "key": "y"}), \
         patch("engines.google_light.run", side_effect=Exception("API timeout")), \
         patch("engines.google_forums.run", return_value=fake_result):
        with patch("sys.argv", ["serpapi_search.py",
                                "--search_phrase", "coffee",
                                "--engines", "google_light", "google_forums"]):
            import serpapi_search
            import importlib
            importlib.reload(serpapi_search)
            serpapi_search.main()
    captured = capsys.readouterr()
    stats_line = [l for l in captured.out.splitlines() if l.startswith("STATS:")][0]
    data = json.loads(stats_line[7:])
    assert "error" in data["engines"]["google_light"]
    assert data["engines"]["google_forums"]["cache_id"] == "uuid-forums"
