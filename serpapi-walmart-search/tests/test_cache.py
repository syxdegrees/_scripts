"""Tests for cache helper functions in serpapi_walmart_search.py."""
import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from serpapi_walmart_search import (
    get_supabase_config,
    _supabase_get,
    _supabase_post,
    strip_serpapi_metadata,
    extract_top_items,
    cache_lookup_search,
    cache_lookup_product,
    cache_lookup_reviews,
    store_search_result,
    store_product_result,
    store_reviews_result,
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
        "search_parameters": {"engine": "walmart", "query": "coffee"},
        "serpapi_pagination": {"next": "https://..."},
        "organic_results": [{"us_item_id": "123", "title": "Coffee"}],
        "search_information": {"total_results": 1000},
    }
    cleaned = strip_serpapi_metadata(response)
    assert "search_metadata" not in cleaned
    assert "search_parameters" not in cleaned
    assert "serpapi_pagination" not in cleaned


def test_strip_serpapi_metadata_keeps_data_keys():
    response = {
        "search_metadata": {"id": "abc"},
        "organic_results": [{"us_item_id": "123"}],
        "search_information": {"total_results": 500},
        "product_result": {"title": "Coffee Maker"},
        "reviews_results": {"reviews": []},
    }
    cleaned = strip_serpapi_metadata(response)
    assert "organic_results" in cleaned
    assert "search_information" in cleaned
    assert "product_result" in cleaned
    assert "reviews_results" in cleaned


def test_strip_serpapi_metadata_does_not_mutate_original():
    response = {
        "search_metadata": {"id": "abc"},
        "organic_results": [{"us_item_id": "123"}],
    }
    strip_serpapi_metadata(response)
    assert "search_metadata" in response


# ── extract_top_items ─────────────────────────────────────────────────────────

def test_extract_top_items_returns_correct_count():
    organic = [{"us_item_id": str(i), "title": f"Product {i}"} for i in range(20)]
    result = extract_top_items(organic, max_items=10)
    assert len(result) == 10
    assert result[0] == (0, "0")
    assert result[9] == (9, "9")


def test_extract_top_items_fewer_available():
    organic = [{"us_item_id": str(i)} for i in range(5)]
    result = extract_top_items(organic, max_items=10)
    assert len(result) == 5


def test_extract_top_items_skips_missing_us_item_id():
    organic = [{"title": "No ID"}, {"us_item_id": "111"}, {"us_item_id": "222"}]
    result = extract_top_items(organic, max_items=10)
    assert len(result) == 2
    assert result[0] == (1, "111")
    assert result[1] == (2, "222")


def test_extract_top_items_empty_list():
    assert extract_top_items([], max_items=10) == []


# ── cache_lookup_search ───────────────────────────────────────────────────────

def test_cache_lookup_search_hit(monkeypatch):
    fake_row = {"id": "uuid-1", "search_phrase": "coffee", "country": "walmart.com"}
    monkeypatch.setattr(
        "serpapi_walmart_search._supabase_get",
        lambda config, table, params: [fake_row]
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_search(config, "coffee", "walmart.com", ttl_days=7)
    assert result == fake_row


def test_cache_lookup_search_miss(monkeypatch):
    monkeypatch.setattr(
        "serpapi_walmart_search._supabase_get",
        lambda config, table, params: []
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_search(config, "coffee", "walmart.com", ttl_days=7)
    assert result is None


def test_cache_lookup_search_passes_correct_params(monkeypatch):
    captured = {}
    def fake_get(config, table, params):
        captured["table"] = table
        captured["params"] = params
        return []
    monkeypatch.setattr("serpapi_walmart_search._supabase_get", fake_get)
    config = {"url": "https://x.supabase.co", "key": "k"}
    cache_lookup_search(config, "protein powder", "walmart.com.mx", ttl_days=3)
    assert captured["table"] == "serpapi_walmart_search"
    assert captured["params"]["search_phrase"] == "eq.protein powder"
    assert captured["params"]["country"] == "eq.walmart.com.mx"
    assert "pages" not in captured["params"]
    assert "fetched_at" in captured["params"]


# ── cache_lookup_product ──────────────────────────────────────────────────────

def test_cache_lookup_product_hit(monkeypatch):
    fake_row = {"id": "uuid-2", "us_item_id": "505002150", "country": "walmart.com"}
    monkeypatch.setattr(
        "serpapi_walmart_search._supabase_get",
        lambda config, table, params: [fake_row]
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_product(config, "505002150", "walmart.com", ttl_days=7)
    assert result == fake_row


def test_cache_lookup_product_miss(monkeypatch):
    monkeypatch.setattr(
        "serpapi_walmart_search._supabase_get",
        lambda config, table, params: []
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_product(config, "505002150", "walmart.com", ttl_days=7)
    assert result is None


def test_cache_lookup_product_passes_correct_params(monkeypatch):
    captured = {}
    def fake_get(config, table, params):
        captured["table"] = table
        captured["params"] = params
        return []
    monkeypatch.setattr("serpapi_walmart_search._supabase_get", fake_get)
    config = {"url": "https://x.supabase.co", "key": "k"}
    cache_lookup_product(config, "505002150", "walmart.com", ttl_days=14)
    assert captured["table"] == "serpapi_walmart_product"
    assert captured["params"]["us_item_id"] == "eq.505002150"
    assert captured["params"]["country"] == "eq.walmart.com"
    assert "fetched_at" in captured["params"]


# ── cache_lookup_reviews ──────────────────────────────────────────────────────

def test_cache_lookup_reviews_hit(monkeypatch):
    fake_row = {"id": "uuid-3", "us_item_id": "505002150", "review_pages": 2}
    monkeypatch.setattr(
        "serpapi_walmart_search._supabase_get",
        lambda config, table, params: [fake_row]
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_reviews(config, "505002150", "walmart.com", review_pages=2, ttl_days=7)
    assert result == fake_row


def test_cache_lookup_reviews_miss(monkeypatch):
    monkeypatch.setattr(
        "serpapi_walmart_search._supabase_get",
        lambda config, table, params: []
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_reviews(config, "505002150", "walmart.com", review_pages=1, ttl_days=7)
    assert result is None


def test_cache_lookup_reviews_passes_correct_params(monkeypatch):
    captured = {}
    def fake_get(config, table, params):
        captured["table"] = table
        captured["params"] = params
        return []
    monkeypatch.setattr("serpapi_walmart_search._supabase_get", fake_get)
    config = {"url": "https://x.supabase.co", "key": "k"}
    cache_lookup_reviews(config, "505002150", "walmart.com", review_pages=3, ttl_days=7)
    assert captured["table"] == "serpapi_walmart_reviews"
    assert captured["params"]["us_item_id"] == "eq.505002150"
    assert captured["params"]["country"] == "eq.walmart.com"
    assert captured["params"]["review_pages"] == "eq.3"
    assert "fetched_at" in captured["params"]


# ── store_search_result ───────────────────────────────────────────────────────

def test_store_search_result_strips_metadata(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-s1"}
    monkeypatch.setattr("serpapi_walmart_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    api_response = {
        "search_metadata": {"id": "abc"},
        "search_parameters": {"engine": "walmart"},
        "serpapi_pagination": {"next": "https://..."},
        "organic_results": [{"us_item_id": "123", "title": "Coffee"}],
        "search_information": {"total_results": 500},
    }
    store_search_result(config, "coffee", "walmart.com", 1, api_response)
    assert "search_metadata" not in inserted
    assert "search_parameters" not in inserted
    assert "serpapi_pagination" not in inserted


def test_store_search_result_maps_section_columns(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-s2"}
    monkeypatch.setattr("serpapi_walmart_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    organic = [{"us_item_id": "111", "title": "Protein"}, {"us_item_id": "222", "title": "Powder"}]
    api_response = {
        "organic_results": organic,
        "search_information": {"total_results": 200},
    }
    store_search_result(config, "protein-powder", "walmart.com", 1, api_response)
    assert inserted["organic_results"] == json.dumps(organic)
    assert inserted["search_phrase"] == "protein-powder"
    assert inserted["country"] == "walmart.com"
    assert inserted["pages"] == 1
    assert inserted["result_count"] == 2


def test_store_search_result_returns_uuid(monkeypatch):
    monkeypatch.setattr(
        "serpapi_walmart_search._supabase_post",
        lambda config, table, row: {"id": "uuid-s3"}
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = store_search_result(config, "coffee", "walmart.com", 1, {"organic_results": []})
    assert result == "uuid-s3"


# ── store_product_result ──────────────────────────────────────────────────────

def test_store_product_result_strips_metadata(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-p1"}
    monkeypatch.setattr("serpapi_walmart_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    api_response = {
        "search_metadata": {"id": "xyz"},
        "search_parameters": {"engine": "walmart_product"},
        "product_result": {"us_item_id": "123", "title": "Protein Powder"},
        "reviews_results": {"ratings": [], "reviews": []},
    }
    store_product_result(config, "123", "walmart.com", api_response)
    assert "search_metadata" not in inserted
    assert "search_parameters" not in inserted


def test_store_product_result_maps_section_columns(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-p2"}
    monkeypatch.setattr("serpapi_walmart_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    product = {"us_item_id": "123", "title": "Protein Powder", "rating": 4.5}
    reviews = {"ratings": [{"stars": 5, "count": 100}], "reviews": []}
    api_response = {"product_result": product, "reviews_results": reviews}
    store_product_result(config, "123", "walmart.com", api_response)
    assert inserted["product_result"] == json.dumps(product)
    assert inserted["reviews_results"] == json.dumps(reviews)
    assert inserted["us_item_id"] == "123"
    assert inserted["country"] == "walmart.com"


def test_store_product_result_returns_uuid(monkeypatch):
    monkeypatch.setattr(
        "serpapi_walmart_search._supabase_post",
        lambda config, table, row: {"id": "uuid-p3"}
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = store_product_result(config, "123", "walmart.com", {"product_result": {}})
    assert result == "uuid-p3"


# ── store_reviews_result ──────────────────────────────────────────────────────

def test_store_reviews_result_strips_metadata(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-r1"}
    monkeypatch.setattr("serpapi_walmart_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    api_response = {
        "search_metadata": {"id": "abc"},
        "search_parameters": {"engine": "walmart_product_reviews"},
        "overall_rating": 4.1,
        "total_count": 3891,
        "reviews": [{"text": "Great", "rating": 5}],
    }
    store_reviews_result(config, "505002150", "walmart.com", 1, api_response)
    assert "search_metadata" not in inserted
    assert "search_parameters" not in inserted


def test_store_reviews_result_maps_scalar_and_jsonb_columns(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-r2"}
    monkeypatch.setattr("serpapi_walmart_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    ratings = [{"stars": 5, "count": 200}, {"stars": 4, "count": 100}]
    reviews = [{"text": "Great product", "rating": 5}]
    product = {"name": "Protein Powder", "url": "https://walmart.com/ip/123"}
    api_response = {
        "overall_rating": 4.1,
        "total_count": 3891,
        "ratings": ratings,
        "reviews": reviews,
        "product": product,
    }
    store_reviews_result(config, "505002150", "walmart.com", 2, api_response)
    assert inserted["overall_rating"] == 4.1
    assert inserted["total_count"] == 3891
    assert inserted["ratings"] == json.dumps(ratings)
    assert inserted["reviews"] == json.dumps(reviews)
    assert inserted["product"] == json.dumps(product)
    assert inserted["us_item_id"] == "505002150"
    assert inserted["country"] == "walmart.com"
    assert inserted["review_pages"] == 2


def test_store_reviews_result_returns_uuid(monkeypatch):
    monkeypatch.setattr(
        "serpapi_walmart_search._supabase_post",
        lambda config, table, row: {"id": "uuid-r3"}
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = store_reviews_result(
        config, "505002150", "walmart.com", 1,
        {"overall_rating": 4.1, "total_count": 100}
    )
    assert result == "uuid-r3"


# ── store_search_product_link ─────────────────────────────────────────────────

def test_store_search_product_link(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update({"table": table, **row})
        return {}
    monkeypatch.setattr("serpapi_walmart_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    store_search_product_link(config, "s-uuid", "p-uuid", position=3)
    assert inserted["table"] == "serpapi_walmart_search_product_link"
    assert inserted["search_cache_id"] == "s-uuid"
    assert inserted["product_cache_id"] == "p-uuid"
    assert inserted["position"] == 3


def test_store_search_product_link_none_position(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {}
    monkeypatch.setattr("serpapi_walmart_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    store_search_product_link(config, "s-uuid", "p-uuid", position=None)
    assert inserted["position"] is None
