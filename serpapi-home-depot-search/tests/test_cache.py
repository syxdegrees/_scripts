"""Tests for cache helper functions in serpapi_home_depot_search.py."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from serpapi_home_depot_search import (
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
        "search_parameters": {"engine": "home_depot", "q": "saw"},
        "serpapi_pagination": {"next": "https://..."},
        "products": [{"product_id": "123", "title": "Circular Saw"}],
        "search_information": {"total_results": 1000},
    }
    cleaned = strip_serpapi_metadata(response)
    assert "search_metadata" not in cleaned
    assert "search_parameters" not in cleaned
    assert "serpapi_pagination" not in cleaned


def test_strip_serpapi_metadata_keeps_data_keys():
    response = {
        "search_metadata": {"id": "abc"},
        "products": [{"product_id": "123"}],
        "search_information": {"total_results": 500},
        "product_results": {"title": "Circular Saw"},
        "taxonomy": {"name": "Circular Saw"},
    }
    cleaned = strip_serpapi_metadata(response)
    assert "products" in cleaned
    assert "search_information" in cleaned
    assert "product_results" in cleaned
    assert "taxonomy" in cleaned


def test_strip_serpapi_metadata_does_not_mutate_original():
    response = {
        "search_metadata": {"id": "abc"},
        "products": [{"product_id": "123"}],
    }
    strip_serpapi_metadata(response)
    assert "search_metadata" in response


# ── extract_top_items ─────────────────────────────────────────────────────────

def test_extract_top_items_returns_correct_count():
    products = [{"product_id": str(i), "title": f"Product {i}"} for i in range(20)]
    result = extract_top_items(products, max_items=10)
    assert len(result) == 10
    assert result[0] == (0, "0")
    assert result[9] == (9, "9")


def test_extract_top_items_fewer_available():
    products = [{"product_id": str(i)} for i in range(5)]
    result = extract_top_items(products, max_items=10)
    assert len(result) == 5


def test_extract_top_items_skips_missing_product_id():
    products = [{"title": "No ID"}, {"product_id": "206123971"}, {"product_id": "206123972"}]
    result = extract_top_items(products, max_items=10)
    assert len(result) == 2
    assert result[0] == (1, "206123971")
    assert result[1] == (2, "206123972")


def test_extract_top_items_empty_list():
    assert extract_top_items([], max_items=10) == []


# ── cache_lookup_search ───────────────────────────────────────────────────────

def test_cache_lookup_search_hit(monkeypatch):
    fake_row = {"id": "uuid-1", "search_phrase": "circular-saw", "domain": "homedepot.com"}
    monkeypatch.setattr(
        "serpapi_home_depot_search._supabase_get",
        lambda config, table, params: [fake_row]
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_search(config, "circular-saw", "homedepot.com", ttl_days=30)
    assert result == fake_row


def test_cache_lookup_search_miss(monkeypatch):
    monkeypatch.setattr(
        "serpapi_home_depot_search._supabase_get",
        lambda config, table, params: []
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_search(config, "circular-saw", "homedepot.com", ttl_days=30)
    assert result is None


def test_cache_lookup_search_passes_correct_params(monkeypatch):
    captured = {}
    def fake_get(config, table, params):
        captured["table"] = table
        captured["params"] = params
        return []
    monkeypatch.setattr("serpapi_home_depot_search._supabase_get", fake_get)
    config = {"url": "https://x.supabase.co", "key": "k"}
    cache_lookup_search(config, "power-drill", "homedepot.ca", ttl_days=30)
    assert captured["table"] == "serpapi_home_depot_search_cache"
    assert captured["params"]["search_phrase"] == "eq.power-drill"
    assert captured["params"]["domain"] == "eq.homedepot.ca"
    assert "pages" not in captured["params"]
    assert "fetched_at" in captured["params"]


# ── cache_lookup_product ──────────────────────────────────────────────────────

def test_cache_lookup_product_hit(monkeypatch):
    fake_row = {"id": "uuid-2", "item_id": "206123971", "domain": "homedepot.com"}
    monkeypatch.setattr(
        "serpapi_home_depot_search._supabase_get",
        lambda config, table, params: [fake_row]
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_product(config, "206123971", "homedepot.com", ttl_days=30)
    assert result == fake_row


def test_cache_lookup_product_miss(monkeypatch):
    monkeypatch.setattr(
        "serpapi_home_depot_search._supabase_get",
        lambda config, table, params: []
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_product(config, "206123971", "homedepot.com", ttl_days=30)
    assert result is None


def test_cache_lookup_product_passes_correct_params(monkeypatch):
    captured = {}
    def fake_get(config, table, params):
        captured["table"] = table
        captured["params"] = params
        return []
    monkeypatch.setattr("serpapi_home_depot_search._supabase_get", fake_get)
    config = {"url": "https://x.supabase.co", "key": "k"}
    cache_lookup_product(config, "206123971", "homedepot.com", ttl_days=30)
    assert captured["table"] == "serpapi_home_depot_product_cache"
    assert captured["params"]["item_id"] == "eq.206123971"
    assert captured["params"]["domain"] == "eq.homedepot.com"
    assert "fetched_at" in captured["params"]


# ── cache_lookup_reviews ──────────────────────────────────────────────────────

def test_cache_lookup_reviews_hit(monkeypatch):
    fake_row = {"id": "uuid-3", "item_id": "206123971", "review_pages": 2}
    monkeypatch.setattr(
        "serpapi_home_depot_search._supabase_get",
        lambda config, table, params: [fake_row]
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_reviews(config, "206123971", "homedepot.com", review_pages=2, ttl_days=30)
    assert result == fake_row


def test_cache_lookup_reviews_miss(monkeypatch):
    monkeypatch.setattr(
        "serpapi_home_depot_search._supabase_get",
        lambda config, table, params: []
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = cache_lookup_reviews(config, "206123971", "homedepot.com", review_pages=1, ttl_days=30)
    assert result is None


def test_cache_lookup_reviews_passes_correct_params(monkeypatch):
    captured = {}
    def fake_get(config, table, params):
        captured["table"] = table
        captured["params"] = params
        return []
    monkeypatch.setattr("serpapi_home_depot_search._supabase_get", fake_get)
    config = {"url": "https://x.supabase.co", "key": "k"}
    cache_lookup_reviews(config, "206123971", "homedepot.com", review_pages=3, ttl_days=30)
    assert captured["table"] == "serpapi_home_depot_reviews_cache"
    assert captured["params"]["item_id"] == "eq.206123971"
    assert captured["params"]["domain"] == "eq.homedepot.com"
    assert captured["params"]["review_pages"] == "eq.3"
    assert "fetched_at" in captured["params"]


# ── store_search_result ───────────────────────────────────────────────────────

def test_store_search_result_strips_metadata(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-s1"}
    monkeypatch.setattr("serpapi_home_depot_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    api_response = {
        "search_metadata": {"id": "abc"},
        "search_parameters": {"engine": "home_depot"},
        "serpapi_pagination": {"next": "https://..."},
        "products": [{"product_id": "123", "title": "Saw"}],
        "search_information": {"total_results": 500},
    }
    store_search_result(config, "circular-saw", "homedepot.com", 1, api_response)
    assert "search_metadata" not in inserted
    assert "search_parameters" not in inserted
    assert "serpapi_pagination" not in inserted


def test_store_search_result_maps_section_columns(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-s2"}
    monkeypatch.setattr("serpapi_home_depot_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    products = [{"product_id": "111", "title": "Saw A"}, {"product_id": "222", "title": "Saw B"}]
    api_response = {
        "products": products,
        "search_information": {"total_results": 200},
    }
    store_search_result(config, "circular-saw", "homedepot.com", 1, api_response)
    assert inserted["products"] == json.dumps(products)
    assert inserted["search_phrase"] == "circular-saw"
    assert inserted["domain"] == "homedepot.com"
    assert inserted["pages"] == 1
    assert inserted["result_count"] == 2


def test_store_search_result_returns_uuid(monkeypatch):
    monkeypatch.setattr(
        "serpapi_home_depot_search._supabase_post",
        lambda config, table, row: {"id": "uuid-s3"}
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = store_search_result(config, "saw", "homedepot.com", 1, {"products": []})
    assert result == "uuid-s3"


# ── store_product_result ──────────────────────────────────────────────────────

def test_store_product_result_strips_metadata(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-p1"}
    monkeypatch.setattr("serpapi_home_depot_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    api_response = {
        "search_metadata": {"id": "xyz"},
        "search_parameters": {"engine": "home_depot_product"},
        "product_results": {"item_id": "123", "title": "Circular Saw"},
    }
    store_product_result(config, "123", "homedepot.com", api_response)
    assert "search_metadata" not in inserted
    assert "search_parameters" not in inserted


def test_store_product_result_maps_section_columns(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-p2"}
    monkeypatch.setattr("serpapi_home_depot_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    product = {"item_id": "123", "title": "Circular Saw", "price": 99.99}
    related = [{"item_id": "456", "title": "Blade"}]
    api_response = {"product_results": product, "related_products": related}
    store_product_result(config, "123", "homedepot.com", api_response)
    assert inserted["product_results"] == json.dumps(product)
    assert inserted["related_products"] == json.dumps(related)
    assert inserted["item_id"] == "123"
    assert inserted["domain"] == "homedepot.com"


def test_store_product_result_returns_uuid(monkeypatch):
    monkeypatch.setattr(
        "serpapi_home_depot_search._supabase_post",
        lambda config, table, row: {"id": "uuid-p3"}
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = store_product_result(config, "123", "homedepot.com", {"product_results": {}})
    assert result == "uuid-p3"


# ── store_reviews_result ──────────────────────────────────────────────────────

def test_store_reviews_result_strips_metadata(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-r1"}
    monkeypatch.setattr("serpapi_home_depot_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    api_response = {
        "search_metadata": {"id": "abc"},
        "search_parameters": {"engine": "home_depot_product_reviews"},
        "overall_rating": 4.5,
        "total_count": 1200,
        "reviews": [{"text": "Great saw", "rating": 5}],
    }
    store_reviews_result(config, "206123971", "homedepot.com", 1, api_response)
    assert "search_metadata" not in inserted
    assert "search_parameters" not in inserted


def test_store_reviews_result_maps_scalar_and_jsonb_columns(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {"id": "uuid-r2"}
    monkeypatch.setattr("serpapi_home_depot_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    ratings = [{"stars": 5, "count": 800}, {"stars": 4, "count": 300}]
    reviews = [{"text": "Great product", "rating": 5}]
    product = {"title": "Circular Saw", "url": "https://homedepot.com/p/123"}
    api_response = {
        "overall_rating": 4.5,
        "total_review": 1200,  # API field name; stored in DB column "total_count"
        "ratings": ratings,
        "reviews": reviews,
        "product": product,
    }
    store_reviews_result(config, "206123971", "homedepot.com", 2, api_response)
    assert inserted["overall_rating"] == 4.5
    assert inserted["total_count"] == 1200
    assert inserted["ratings"] == json.dumps(ratings)
    assert inserted["reviews"] == json.dumps(reviews)
    assert inserted["product"] == json.dumps(product)
    assert inserted["item_id"] == "206123971"
    assert inserted["domain"] == "homedepot.com"
    assert inserted["review_pages"] == 2


def test_store_reviews_result_returns_uuid(monkeypatch):
    monkeypatch.setattr(
        "serpapi_home_depot_search._supabase_post",
        lambda config, table, row: {"id": "uuid-r3"}
    )
    config = {"url": "https://x.supabase.co", "key": "k"}
    result = store_reviews_result(
        config, "206123971", "homedepot.com", 1,
        {"overall_rating": 4.5, "total_count": 1200}
    )
    assert result == "uuid-r3"


# ── store_search_product_link ─────────────────────────────────────────────────

def test_store_search_product_link(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update({"table": table, **row})
        return {}
    monkeypatch.setattr("serpapi_home_depot_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    store_search_product_link(config, "s-uuid", "p-uuid", position=3)
    assert inserted["table"] == "serpapi_home_depot_search_product_link"
    assert inserted["search_cache_id"] == "s-uuid"
    assert inserted["product_cache_id"] == "p-uuid"
    assert inserted["position"] == 3


def test_store_search_product_link_none_position(monkeypatch):
    inserted = {}
    def fake_post(config, table, row):
        inserted.update(row)
        return {}
    monkeypatch.setattr("serpapi_home_depot_search._supabase_post", fake_post)
    config = {"url": "https://x.supabase.co", "key": "k"}
    store_search_product_link(config, "s-uuid", "p-uuid", position=None)
    assert inserted["position"] is None
