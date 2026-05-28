import json
import pytest
from unittest.mock import patch, MagicMock
from tests.test_helpers import set_env
from shared.db import (
    get_supabase_config, normalize_params, cache_lookup,
    insert_row, _ttl_cutoff
)


def test_get_supabase_config_success(monkeypatch):
    set_env(monkeypatch)
    config = get_supabase_config()
    assert config["url"] == "https://test.supabase.co"
    assert config["key"] == "test-service-role-key"


def test_get_supabase_config_missing_url(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "key")
    with pytest.raises(SystemExit):
        get_supabase_config()


def test_get_supabase_config_missing_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    with pytest.raises(SystemExit):
        get_supabase_config()


def test_normalize_params_sorts_keys():
    params = {"z": 1, "a": 2, "m": 3}
    result = json.loads(normalize_params(params))
    assert list(result.keys()) == ["a", "m", "z"]


def test_normalize_params_identical_for_same_input():
    p1 = {"gl": "us", "q": "coffee", "hl": "en"}
    p2 = {"hl": "en", "q": "coffee", "gl": "us"}
    assert normalize_params(p1) == normalize_params(p2)


def test_cache_lookup_returns_row_on_hit(monkeypatch):
    set_env(monkeypatch)
    config = get_supabase_config()
    fake_row = {"id": "uuid-123", "search_phrase": "coffee"}
    mock_resp = MagicMock()
    mock_resp.json.return_value = [fake_row]
    mock_resp.raise_for_status = MagicMock()
    with patch("shared.db.requests.get", return_value=mock_resp):
        result = cache_lookup(config, "some_table", "coffee", {"q": "coffee"}, 30)
    assert result == fake_row


def test_cache_lookup_returns_none_on_miss(monkeypatch):
    set_env(monkeypatch)
    config = get_supabase_config()
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    mock_resp.raise_for_status = MagicMock()
    with patch("shared.db.requests.get", return_value=mock_resp):
        result = cache_lookup(config, "some_table", "coffee", {"q": "coffee"}, 30)
    assert result is None


def test_insert_row_returns_id(monkeypatch):
    set_env(monkeypatch)
    config = get_supabase_config()
    mock_resp = MagicMock()
    mock_resp.json.return_value = [{"id": "new-uuid"}]
    mock_resp.raise_for_status = MagicMock()
    with patch("shared.db.requests.post", return_value=mock_resp):
        result = insert_row(config, "some_table", {"search_phrase": "coffee"})
    assert result == "new-uuid"
