"""Tests for cache helper functions in serpapi_apple_app_store_search.py."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from serpapi_apple_app_store_search import (
    get_supabase_config,
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
        "search_parameters": {"engine": "apple_app_store", "term": "fitness"},
        "serpapi_pagination": {"next": "https://..."},
        "organic_results": [{"id": 123, "title": "Fitness App"}],
        "search_information": {"results_count": 10},
    }
    cleaned = strip_serpapi_metadata(response)
    assert "search_metadata" not in cleaned
    assert "search_parameters" not in cleaned
    assert "serpapi_pagination" not in cleaned


def test_strip_serpapi_metadata_keeps_data_keys():
    response = {
        "search_metadata": {"id": "abc"},
        "organic_results": [{"id": 123}],
        "search_information": {"results_count": 10},
    }
    cleaned = strip_serpapi_metadata(response)
    assert "organic_results" in cleaned
    assert "search_information" in cleaned


def test_strip_serpapi_metadata_does_not_mutate_original():
    response = {
        "search_metadata": {"id": "abc"},
        "organic_results": [{"id": 123}],
    }
    strip_serpapi_metadata(response)
    assert "search_metadata" in response


# ── extract_top_items ─────────────────────────────────────────────────────────

def test_extract_top_items_returns_correct_count():
    organic = [{"id": i, "title": f"App {i}"} for i in range(20)]
    result = extract_top_items(organic, max_items=10)
    assert len(result) == 10
    assert result[0] == (0, "0")
    assert result[9] == (9, "9")


def test_extract_top_items_fewer_available():
    organic = [{"id": i} for i in range(5)]
    result = extract_top_items(organic, max_items=10)
    assert len(result) == 5


def test_extract_top_items_skips_missing_id():
    organic = [{"title": "No ID"}, {"id": 899247664}, {"id": 534220544}]
    result = extract_top_items(organic, max_items=10)
    assert len(result) == 2
    assert result[0] == (1, "899247664")
    assert result[1] == (2, "534220544")


def test_extract_top_items_empty_list():
    assert extract_top_items([], max_items=10) == []


# ── cache_lookup_search ───────────────────────────────────────────────────────

def test_cache_lookup_search_hit(monkeypatch):
    fake_row = {"id": "uuid-1", "search_phrase": "fitness-tracker", "country": "us"}
    monkeypatch.setattr(
        "serpapi_apple_app_store_search._supabase_get",
        lambda config, table, params: [fake_row]
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_search(config, "fitness-tracker", "us", pages=1, ttl_days=30)
    assert result == fake_row


def test_cache_lookup_search_miss(monkeypatch):
    monkeypatch.setattr(
        "serpapi_apple_app_store_search._supabase_get",
        lambda config, table, params: []
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_search(config, "fitness-tracker", "us", pages=1, ttl_days=30)
    assert result is None


def test_cache_lookup_search_passes_correct_params(monkeypatch):
    captured = {}
    def fake_get(config, table, params):
        captured["table"] = table
        captured["params"] = params
        return []
    monkeypatch.setattr("serpapi_apple_app_store_search._supabase_get", fake_get)
    config = {"url": "https://x.supabase.co", "key": "k"}
    cache_lookup_search(config, "workout-app", "gb", pages=2, ttl_days=30)
    assert captured["table"] == "serpapi_apple_app_store_search_cache"
    assert captured["params"]["search_phrase"] == "eq.workout-app"
    assert captured["params"]["country"] == "eq.gb"
    assert captured["params"]["pages"] == "eq.2"
    assert "fetched_at" in captured["params"]


# ── cache_lookup_product ──────────────────────────────────────────────────────

def test_cache_lookup_product_hit(monkeypatch):
    fake_row = {"id": "uuid-2", "app_id": "899247664", "country": "us"}
    monkeypatch.setattr(
        "serpapi_apple_app_store_search._supabase_get",
        lambda config, table, params: [fake_row]
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_product(config, "899247664", "us", ttl_days=30)
    assert result == fake_row


def test_cache_lookup_product_miss(monkeypatch):
    monkeypatch.setattr(
        "serpapi_apple_app_store_search._supabase_get",
        lambda config, table, params: []
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_product(config, "899247664", "us", ttl_days=30)
    assert result is None


def test_cache_lookup_product_passes_correct_params(monkeypatch):
    captured = {}
    def fake_get(config, table, params):
        captured["table"] = table
        captured["params"] = params
        return []
    monkeypatch.setattr("serpapi_apple_app_store_search._supabase_get", fake_get)
    config = {"url": "https://x.supabase.co", "key": "k"}
    cache_lookup_product(config, "899247664", "us", ttl_days=30)
    assert captured["table"] == "serpapi_apple_app_store_product_cache"
    assert captured["params"]["app_id"] == "eq.899247664"
    assert captured["params"]["country"] == "eq.us"
    assert "fetched_at" in captured["params"]


# ── cache_lookup_reviews ──────────────────────────────────────────────────────

def test_cache_lookup_reviews_hit(monkeypatch):
    fake_row = {"id": "uuid-3", "app_id": "899247664", "review_pages": 2}
    monkeypatch.setattr(
        "serpapi_apple_app_store_search._supabase_get",
        lambda config, table, params: [fake_row]
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_reviews(config, "899247664", "us", review_pages=2, ttl_days=30)
    assert result == fake_row


def test_cache_lookup_reviews_miss(monkeypatch):
    monkeypatch.setattr(
        "serpapi_apple_app_store_search._supabase_get",
        lambda config, table, params: []
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_reviews(config, "899247664", "us", review_pages=1, ttl_days=30)
    assert result is None


def test_cache_lookup_reviews_passes_correct_params(monkeypatch):
    captured = {}
    def fake_get(config, table, params):
        captured["table"] = table
        captured["params"] = params
        return []
    monkeypatch.setattr("serpapi_apple_app_store_search._supabase_get", fake_get)
    config = {"url": "https://x.supabase.co", "key": "k"}
    cache_lookup_reviews(config, "899247664", "us", review_pages=3, ttl_days=30)
    assert captured["table"] == "serpapi_apple_app_store_reviews_cache"
    assert captured["params"]["app_id"] == "eq.899247664"
    assert captured["params"]["country"] == "eq.us"
    assert captured["params"]["review_pages"] == "eq.3"
    assert "fetched_at" in captured["params"]


# ── store_search_result ───────────────────────────────────────────────────────

def test_store_search_result_strips_metadata(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-s1"}
    monkeypatch.setattr("serpapi_apple_app_store_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    api_response = {
        "search_metadata": {"id": "abc"},
        "search_parameters": {"engine": "apple_app_store"},
        "serpapi_pagination": {"next": "https://..."},
        "organic_results": [{"id": 123, "title": "Fitness App"}],
        "search_information": {"results_count": 10},
    }
    store_search_result(config, "fitness-tracker", "us", 1, api_response)
    assert "search_metadata" not in inserted
    assert "search_parameters" not in inserted
    assert "serpapi_pagination" not in inserted


def test_store_search_result_maps_section_columns(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-s2"}
    monkeypatch.setattr("serpapi_apple_app_store_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    organic = [{"id": 111, "title": "App A"}, {"id": 222, "title": "App B"}]
    api_response = {
        "organic_results": organic,
        "search_information": {"results_count": 2},
    }
    store_search_result(config, "fitness-tracker", "us", 1, api_response)
    assert inserted["organic_results"] == json.dumps(organic)
    assert inserted["search_phrase"] == "fitness-tracker"
    assert inserted["country"] == "us"
    assert inserted["pages"] == 1
    assert inserted["result_count"] == 2


def test_store_search_result_returns_uuid(monkeypatch):
    monkeypatch.setattr(
        "serpapi_apple_app_store_search._supabase_post",
        lambda config, table, row: {"id": "uuid-s3"}
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = store_search_result(config, "fitness", "us", 1, {"organic_results": []})
    assert result == "uuid-s3"


# ── store_product_result ──────────────────────────────────────────────────────

def test_store_product_result_strips_metadata(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-p1"}
    monkeypatch.setattr("serpapi_apple_app_store_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    api_response = {
        "search_metadata": {"id": "xyz"},
        "search_parameters": {"engine": "apple_product"},
        "title": "TestFlight",
        "id": "899247664",
        "description": "Beta testing app",
    }
    store_product_result(config, "899247664", "us", api_response)
    assert "search_metadata" not in inserted
    assert "search_parameters" not in inserted


def test_store_product_result_stores_full_response_as_product_results(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-p2"}
    monkeypatch.setattr("serpapi_apple_app_store_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    api_response = {
        "title": "TestFlight",
        "id": "899247664",
        "description": "Beta testing app",
        "rating": 4.74,
        "developer": {"name": "Apple", "link": "https://apple.com"},
    }
    store_product_result(config, "899247664", "us", api_response)
    stored = json.loads(inserted["product_results"])
    assert stored["title"] == "TestFlight"
    assert stored["rating"] == 4.74
    assert inserted["app_id"] == "899247664"
    assert inserted["country"] == "us"


def test_store_product_result_returns_uuid(monkeypatch):
    monkeypatch.setattr(
        "serpapi_apple_app_store_search._supabase_post",
        lambda config, table, row: {"id": "uuid-p3"}
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = store_product_result(config, "899247664", "us", {"title": "App"})
    assert result == "uuid-p3"


# ── store_reviews_result ──────────────────────────────────────────────────────

def test_store_reviews_result_strips_metadata(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-r1"}
    monkeypatch.setattr("serpapi_apple_app_store_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    api_response = {
        "search_metadata": {"id": "abc"},
        "search_parameters": {"engine": "apple_reviews"},
        "reviews": [{"id": "111", "text": "Great app", "rating": 5}],
    }
    store_reviews_result(config, "899247664", "us", 1, api_response)
    assert "search_metadata" not in inserted
    assert "search_parameters" not in inserted


def test_store_reviews_result_maps_jsonb_columns(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-r2"}
    monkeypatch.setattr("serpapi_apple_app_store_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    search_info = {"total_page_count": 8, "results_count": 25}
    reviews = [{"id": "111", "text": "Great app", "rating": 5}]
    api_response = {
        "search_information": search_info,
        "reviews": reviews,
    }
    store_reviews_result(config, "899247664", "us", 2, api_response)
    assert inserted["search_information"] == json.dumps(search_info)
    assert inserted["reviews"] == json.dumps(reviews)
    assert inserted["app_id"] == "899247664"
    assert inserted["country"] == "us"
    assert inserted["review_pages"] == 2


def test_store_reviews_result_returns_uuid(monkeypatch):
    monkeypatch.setattr(
        "serpapi_apple_app_store_search._supabase_post",
        lambda config, table, row: {"id": "uuid-r3"}
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = store_reviews_result(
        config, "899247664", "us", 1,
        {"reviews": []}
    )
    assert result == "uuid-r3"


# ── store_search_product_link ─────────────────────────────────────────────────

def test_store_search_product_link(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update({"table": table, **row})
        return {}
    monkeypatch.setattr("serpapi_apple_app_store_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    store_search_product_link(config, "s-uuid", "p-uuid", position=3)
    assert inserted["table"] == "serpapi_apple_app_store_search_product_link"
    assert inserted["search_cache_id"] == "s-uuid"
    assert inserted["product_cache_id"] == "p-uuid"
    assert inserted["position"] == 3


def test_store_search_product_link_none_position(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {}
    monkeypatch.setattr("serpapi_apple_app_store_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    store_search_product_link(config, "s-uuid", "p-uuid", position=None)
    assert inserted["position"] is None
