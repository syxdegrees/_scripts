"""Tests for cache helper functions in serpapi_amazon_search.py."""
import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from serpapi_amazon_search import (
    get_supabase_config,
    _supabase_get,
    _supabase_post,
    strip_serpapi_metadata,
    extract_top_asins,
    cache_lookup_search,
    cache_lookup_product,
    store_search_result,
    store_product_result,
    store_search_product_link,
)


# ── get_supabase_config ───────────────────────────────────────────────────────

def test_get_supabase_config_returns_url_and_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-secret")
    config = get_supabase_config()
    assert config["url"] == "https://abc.supabase.co"
    assert config["key"] == "test-secret"


def test_get_supabase_config_missing_url_exits(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-secret")
    import pytest
    with pytest.raises(SystemExit):
        get_supabase_config()


def test_get_supabase_config_missing_key_exits(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    import pytest
    with pytest.raises(SystemExit):
        get_supabase_config()


# ── strip_serpapi_metadata ────────────────────────────────────────────────────

def test_strip_serpapi_metadata_removes_housekeeping_keys():
    response = {
        "search_metadata": {"id": "abc", "status": "Success"},
        "search_parameters": {"engine": "amazon", "k": "coffee"},
        "serpapi_pagination": {"next": "https://..."},
        "organic_results": [{"asin": "B001", "title": "Coffee"}],
        "search_information": {"total_results": 1000},
    }
    cleaned = strip_serpapi_metadata(response)
    assert "search_metadata" not in cleaned
    assert "search_parameters" not in cleaned
    assert "serpapi_pagination" not in cleaned


def test_strip_serpapi_metadata_keeps_data_keys():
    response = {
        "search_metadata": {"id": "abc"},
        "organic_results": [{"asin": "B001"}],
        "related_searches": [{"query": "espresso"}],
        "product_results": {"title": "Coffee Maker"},
        "reviews_information": {"summary": {"text": "Great"}},
    }
    cleaned = strip_serpapi_metadata(response)
    assert "organic_results" in cleaned
    assert "related_searches" in cleaned
    assert "product_results" in cleaned
    assert "reviews_information" in cleaned


def test_strip_serpapi_metadata_does_not_mutate_original():
    response = {
        "search_metadata": {"id": "abc"},
        "organic_results": [{"asin": "B001"}],
    }
    strip_serpapi_metadata(response)
    assert "search_metadata" in response


# ── extract_top_asins ─────────────────────────────────────────────────────────

def test_extract_top_asins_returns_correct_count():
    organic = [{"asin": f"B{i:03d}", "title": f"Product {i}"} for i in range(20)]
    result = extract_top_asins(organic, max_asins=10)
    assert len(result) == 10
    assert result[0] == (0, "B000")
    assert result[9] == (9, "B009")


def test_extract_top_asins_fewer_available():
    organic = [{"asin": f"B{i:03d}"} for i in range(5)]
    result = extract_top_asins(organic, max_asins=10)
    assert len(result) == 5


def test_extract_top_asins_skips_missing_asin():
    organic = [{"title": "No ASIN"}, {"asin": "B001"}, {"asin": "B002"}]
    result = extract_top_asins(organic, max_asins=10)
    assert len(result) == 2
    assert result[0] == (1, "B001")
    assert result[1] == (2, "B002")


def test_extract_top_asins_empty_list():
    assert extract_top_asins([], max_asins=10) == []


# ── cache_lookup_search ───────────────────────────────────────────────────────

def test_cache_lookup_search_hit(monkeypatch):
    fake_row = {"id": "uuid-1", "search_phrase": "coffee", "country": "amazon.com"}
    monkeypatch.setattr(
        "serpapi_amazon_search._supabase_get",
        lambda config, table, params: [fake_row]
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_search(config, "coffee", "amazon.com", pages=1, ttl_days=7)
    assert result == fake_row


def test_cache_lookup_search_miss(monkeypatch):
    monkeypatch.setattr(
        "serpapi_amazon_search._supabase_get",
        lambda config, table, params: []
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_search(config, "coffee", "amazon.com", pages=1, ttl_days=7)
    assert result is None


def test_cache_lookup_search_passes_correct_params(monkeypatch):
    captured = {}
    def fake_get(config, table, params):
        captured["table"] = table
        captured["params"] = params
        return []
    monkeypatch.setattr("serpapi_amazon_search._supabase_get", fake_get)
    config = {"url": "https://x.supabase.co", "key": "k"}
    cache_lookup_search(config, "espresso machine", "amazon.co.uk", pages=2, ttl_days=3)
    assert captured["table"] == "serpapi_amazon_search_cache"
    assert captured["params"]["search_phrase"] == "eq.espresso machine"
    assert captured["params"]["country"] == "eq.amazon.co.uk"
    assert captured["params"]["pages"] == "eq.2"
    assert "fetched_at" in captured["params"]


# ── cache_lookup_product ──────────────────────────────────────────────────────

def test_cache_lookup_product_hit(monkeypatch):
    fake_row = {"id": "uuid-2", "asin": "B001", "country": "amazon.com"}
    monkeypatch.setattr(
        "serpapi_amazon_search._supabase_get",
        lambda config, table, params: [fake_row]
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_product(config, "B001", "amazon.com", ttl_days=7)
    assert result == fake_row


def test_cache_lookup_product_miss(monkeypatch):
    monkeypatch.setattr(
        "serpapi_amazon_search._supabase_get",
        lambda config, table, params: []
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_product(config, "B001", "amazon.com", ttl_days=7)
    assert result is None


def test_cache_lookup_product_passes_correct_params(monkeypatch):
    captured = {}
    def fake_get(config, table, params):
        captured["table"] = table
        captured["params"] = params
        return []
    monkeypatch.setattr("serpapi_amazon_search._supabase_get", fake_get)
    config = {"url": "https://x.supabase.co", "key": "k"}
    cache_lookup_product(config, "B09XXXXX", "amazon.com", ttl_days=14)
    assert captured["table"] == "serpapi_amazon_product_cache"
    assert captured["params"]["asin"] == "eq.B09XXXXX"
    assert captured["params"]["country"] == "eq.amazon.com"
    assert "fetched_at" in captured["params"]


# ── store_search_result ───────────────────────────────────────────────────────

def test_store_search_result_strips_metadata(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-s1"}
    monkeypatch.setattr("serpapi_amazon_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    api_response = {
        "search_metadata": {"id": "abc"},
        "search_parameters": {"engine": "amazon"},
        "serpapi_pagination": {"next": "https://..."},
        "organic_results": [{"asin": "B001", "title": "Coffee"}],
        "search_information": {"total_results": 500},
    }
    store_search_result(config, "coffee", "amazon.com", 1, api_response)
    assert "search_metadata" not in inserted
    assert "search_parameters" not in inserted
    assert "serpapi_pagination" not in inserted


def test_store_search_result_maps_section_columns(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-s2"}
    monkeypatch.setattr("serpapi_amazon_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    organic = [{"asin": "B001", "title": "Coffee"}, {"asin": "B002", "title": "Espresso"}]
    api_response = {"organic_results": organic, "related_searches": [{"query": "espresso"}]}
    store_search_result(config, "coffee", "amazon.com", 1, api_response)
    assert inserted["organic_results"] == json.dumps(organic)
    assert inserted["search_phrase"] == "coffee"
    assert inserted["country"] == "amazon.com"
    assert inserted["pages"] == 1
    assert inserted["result_count"] == 2


def test_store_search_result_returns_uuid(monkeypatch):
    monkeypatch.setattr(
        "serpapi_amazon_search._supabase_post",
        lambda config, table, row: {"id": "uuid-s3"}
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = store_search_result(config, "coffee", "amazon.com", 1, {"organic_results": []})
    assert result == "uuid-s3"


# ── store_product_result ──────────────────────────────────────────────────────

def test_store_product_result_strips_metadata(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-p1"}
    monkeypatch.setattr("serpapi_amazon_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    api_response = {
        "search_metadata": {"id": "xyz"},
        "search_parameters": {"engine": "amazon_product"},
        "product_results": {"asin": "B001", "title": "Coffee Maker"},
        "reviews_information": {"summary": {"text": "Great product"}},
    }
    store_product_result(config, "B001", "amazon.com", api_response)
    assert "search_metadata" not in inserted
    assert "search_parameters" not in inserted


def test_store_product_result_maps_section_columns(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-p2"}
    monkeypatch.setattr("serpapi_amazon_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    product = {"asin": "B001", "title": "Coffee Maker", "rating": 4.5}
    reviews = {"summary": {"text": "Great"}}
    api_response = {"product_results": product, "reviews_information": reviews}
    store_product_result(config, "B001", "amazon.com", api_response)
    assert inserted["product_results"] == json.dumps(product)
    assert inserted["reviews_information"] == json.dumps(reviews)
    assert inserted["asin"] == "B001"
    assert inserted["country"] == "amazon.com"


def test_store_product_result_returns_uuid(monkeypatch):
    monkeypatch.setattr(
        "serpapi_amazon_search._supabase_post",
        lambda config, table, row: {"id": "uuid-p3"}
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = store_product_result(config, "B001", "amazon.com", {"product_results": {}})
    assert result == "uuid-p3"


# ── store_search_product_link ─────────────────────────────────────────────────

def test_store_search_product_link(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update({"table": table, **row})
        return {}
    monkeypatch.setattr("serpapi_amazon_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    store_search_product_link(config, "s-uuid", "p-uuid", position=3)
    assert inserted["table"] == "serpapi_amazon_search_product_link"
    assert inserted["search_cache_id"] == "s-uuid"
    assert inserted["product_cache_id"] == "p-uuid"
    assert inserted["position"] == 3


def test_store_search_product_link_none_position(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {}
    monkeypatch.setattr("serpapi_amazon_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    store_search_product_link(config, "s-uuid", "p-uuid", position=None)
    assert inserted["position"] is None
