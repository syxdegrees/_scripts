import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import serpapi_google_play_search as m

CONFIG = {"url": "https://fake.supabase.co", "key": "fake-key"}


# ── strip_serpapi_metadata ────────────────────────────────────────────────────

def test_strip_serpapi_metadata_removes_keys():
    response = {
        "search_metadata": {"id": "abc"},
        "search_parameters": {"engine": "google_play"},
        "serpapi_pagination": {"next": "..."},
        "organic_results": [{"product_id": "com.example.app"}],
    }
    cleaned = m.strip_serpapi_metadata(response)
    assert "search_metadata" not in cleaned
    assert "search_parameters" not in cleaned
    assert "serpapi_pagination" not in cleaned


def test_strip_serpapi_metadata_keeps_data():
    response = {
        "search_metadata": {"id": "abc"},
        "organic_results": [{"product_id": "com.example.app"}],
        "product_results": {"title": "Fitness App"},
    }
    cleaned = m.strip_serpapi_metadata(response)
    assert "organic_results" in cleaned
    assert "product_results" in cleaned


# ── extract_top_items ─────────────────────────────────────────────────────────

def _make_sections(items_per_section):
    """Build organic_results with given counts. Returns (sections, flat_ids)."""
    sections = []
    flat_ids = []
    counter = 0
    for count in items_per_section:
        items = []
        for _ in range(count):
            pid = f"com.example.app{counter}"
            items.append({"product_id": pid, "title": f"App {counter}"})
            flat_ids.append(pid)
            counter += 1
        sections.append({"title": f"Section {len(sections)}", "items": items})
    return sections, flat_ids


def test_extract_top_items_flattens_sections():
    sections, flat_ids = _make_sections([3, 3])
    result = m.extract_top_items(sections, max_items=10)
    assert len(result) == 6
    positions = [r[0] for r in result]
    ids = [r[1] for r in result]
    assert positions == list(range(6))
    assert ids == flat_ids


def test_extract_top_items_respects_max_items():
    sections, flat_ids = _make_sections([10, 10])
    result = m.extract_top_items(sections, max_items=5)
    assert len(result) == 5
    assert [r[1] for r in result] == flat_ids[:5]


def test_extract_top_items_fewer_available():
    sections, flat_ids = _make_sections([2, 1])
    result = m.extract_top_items(sections, max_items=10)
    assert len(result) == 3
    assert [r[1] for r in result] == flat_ids


def test_extract_top_items_skips_missing_product_id():
    sections = [
        {"title": "S1", "items": [
            {"title": "No ID"},
            {"product_id": "com.example.good", "title": "Has ID"},
            {"product_id": "", "title": "Empty ID"},
        ]},
    ]
    result = m.extract_top_items(sections, max_items=10)
    assert len(result) == 1
    assert result[0][1] == "com.example.good"


# ── cache_lookup_search ───────────────────────────────────────────────────────

def test_cache_lookup_search_hit(monkeypatch):
    row = {"id": "uuid-search-1", "search_phrase": "fitness-apps", "fetched_at": "2026-05-27T00:00:00+00:00"}
    monkeypatch.setattr(m, "_supabase_get", lambda config, table, params: [row])
    result = m.cache_lookup_search(CONFIG, "fitness-apps", "apps", "us", "en", 30)
    assert result == row


def test_cache_lookup_search_miss_stale(monkeypatch):
    monkeypatch.setattr(m, "_supabase_get", lambda config, table, params: [])
    result = m.cache_lookup_search(CONFIG, "fitness-apps", "apps", "us", "en", 30)
    assert result is None


def test_cache_lookup_search_miss_not_found(monkeypatch):
    monkeypatch.setattr(m, "_supabase_get", lambda config, table, params: [])
    result = m.cache_lookup_search(CONFIG, "no-results", "apps", "us", "en", 30)
    assert result is None


# ── cache_lookup_product ──────────────────────────────────────────────────────

def test_cache_lookup_product_hit_no_reviews(monkeypatch):
    row = {"id": "uuid-prod-1", "product_id": "com.example.app", "with_reviews": False}
    monkeypatch.setattr(m, "_supabase_get", lambda config, table, params: [row])
    result = m.cache_lookup_product(CONFIG, "com.example.app", "apps", "us", "en", False, 30)
    assert result == row


def test_cache_lookup_product_hit_with_reviews_required(monkeypatch):
    row = {"id": "uuid-prod-2", "product_id": "com.example.app", "with_reviews": True}

    def fake_get(config, table, params):
        assert params.get("with_reviews") == "eq.true"
        return [row]

    monkeypatch.setattr(m, "_supabase_get", fake_get)
    result = m.cache_lookup_product(CONFIG, "com.example.app", "apps", "us", "en", True, 30)
    assert result == row


def test_cache_lookup_product_miss_reviews_required_but_not_cached(monkeypatch):
    monkeypatch.setattr(m, "_supabase_get", lambda config, table, params: [])
    result = m.cache_lookup_product(CONFIG, "com.example.app", "apps", "us", "en", True, 30)
    assert result is None


def test_cache_lookup_product_no_reviews_does_not_filter_with_reviews(monkeypatch):
    """with_reviews=False must NOT add the with_reviews filter (accepts any cached row)."""
    captured = {}

    def fake_get(config, table, params):
        captured["params"] = params
        return []

    monkeypatch.setattr(m, "_supabase_get", fake_get)
    m.cache_lookup_product(CONFIG, "com.example.app", "apps", "us", "en", False, 30)
    assert "with_reviews" not in captured["params"]


def test_cache_lookup_product_miss_stale(monkeypatch):
    monkeypatch.setattr(m, "_supabase_get", lambda config, table, params: [])
    result = m.cache_lookup_product(CONFIG, "com.example.app", "apps", "us", "en", False, 30)
    assert result is None


# ── store_search_result ───────────────────────────────────────────────────────

def test_store_search_result_strips_metadata(monkeypatch):
    captured = {}

    def fake_post(config, table, row):
        captured["row"] = row
        return {"id": "uuid-search-1"}

    monkeypatch.setattr(m, "_supabase_post", fake_post)
    api_response = {
        "search_metadata": {"id": "abc"},
        "search_parameters": {"engine": "google_play"},
        "serpapi_pagination": {},
        "organic_results": [{"product_id": "com.example.app"}],
    }
    m.store_search_result(CONFIG, "fitness-apps", "apps", "us", "en", api_response)
    row = captured["row"]
    assert "search_metadata" not in str(row)
    assert "search_parameters" not in str(row)
    assert "serpapi_pagination" not in str(row)


def test_store_search_result_stores_organic_results(monkeypatch):
    captured = {}

    def fake_post(config, table, row):
        captured["row"] = row
        return {"id": "uuid-search-1"}

    monkeypatch.setattr(m, "_supabase_post", fake_post)
    organic = [{"title": "S1", "items": [{"product_id": "com.example.app"}]}]
    api_response = {"organic_results": organic}
    m.store_search_result(CONFIG, "fitness-apps", "apps", "us", "en", api_response)
    assert "organic_results" in captured["row"]
    assert json.loads(captured["row"]["organic_results"]) == organic


# ── store_product_result ──────────────────────────────────────────────────────

def test_store_product_result_strips_metadata(monkeypatch):
    captured = {}

    def fake_post(config, table, row):
        captured["row"] = row
        return {"id": "uuid-prod-1"}

    monkeypatch.setattr(m, "_supabase_post", fake_post)
    api_response = {
        "search_metadata": {"id": "abc"},
        "product_results": {"title": "Fitness App"},
    }
    m.store_product_result(CONFIG, "com.example.app", "apps", "us", "en", False, api_response)
    row = captured["row"]
    assert "search_metadata" not in str(row.get("product_results", ""))


def test_store_product_result_stores_product_results(monkeypatch):
    captured = {}

    def fake_post(config, table, row):
        captured["row"] = row
        return {"id": "uuid-prod-1"}

    monkeypatch.setattr(m, "_supabase_post", fake_post)
    product = {"title": "Fitness App", "rating": 4.5}
    api_response = {"product_results": product}
    m.store_product_result(CONFIG, "com.example.app", "apps", "us", "en", False, api_response)
    assert "product_results" in captured["row"]
    assert json.loads(captured["row"]["product_results"]) == product


def test_store_product_result_stores_reviews_when_with_reviews_true(monkeypatch):
    captured = {}

    def fake_post(config, table, row):
        captured["row"] = row
        return {"id": "uuid-prod-2"}

    monkeypatch.setattr(m, "_supabase_post", fake_post)
    reviews = [{"rating": 5, "text": "Great!"}]
    api_response = {"product_results": {"title": "App"}, "reviews": reviews}
    m.store_product_result(CONFIG, "com.example.app", "apps", "us", "en", True, api_response)
    assert "reviews" in captured["row"]
    assert json.loads(captured["row"]["reviews"]) == reviews
    assert captured["row"]["with_reviews"] is True


def test_store_product_result_reviews_null_when_with_reviews_false(monkeypatch):
    captured = {}

    def fake_post(config, table, row):
        captured["row"] = row
        return {"id": "uuid-prod-3"}

    monkeypatch.setattr(m, "_supabase_post", fake_post)
    api_response = {"product_results": {"title": "App"}, "reviews": [{"rating": 5}]}
    m.store_product_result(CONFIG, "com.example.app", "apps", "us", "en", False, api_response)
    assert "reviews" not in captured["row"]
    assert captured["row"]["with_reviews"] is False


# ── store_search_product_link ─────────────────────────────────────────────────

def test_store_search_product_link(monkeypatch):
    captured = {}

    def fake_post(config, table, row):
        captured["table"] = table
        captured["row"] = row
        return {"id": "uuid-link-1"}

    monkeypatch.setattr(m, "_supabase_post", fake_post)
    m.store_search_product_link(CONFIG, "search-uuid", "product-uuid", 3)
    assert captured["table"] == "serpapi_google_play_search_product_link"
    assert captured["row"]["search_cache_id"] == "search-uuid"
    assert captured["row"]["product_cache_id"] == "product-uuid"
    assert captured["row"]["position"] == 3
