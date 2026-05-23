import sys
import json
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── clean_search_term ────────────────────────────────────────────────────────

def test_clean_search_term_spaces():
    from serpapi_amazon_test import clean_search_term
    assert clean_search_term("weight loss supplements") == "weight-loss-supplements"


def test_clean_search_term_lowercases():
    from serpapi_amazon_test import clean_search_term
    assert clean_search_term("KETO Diet") == "keto-diet"


def test_clean_search_term_strips_special_chars():
    from serpapi_amazon_test import clean_search_term
    assert clean_search_term("organic & natural!") == "organic-natural"


def test_clean_search_term_collapses_hyphens():
    from serpapi_amazon_test import clean_search_term
    assert clean_search_term("a  b") == "a-b"


# ── build_filename ───────────────────────────────────────────────────────────

def test_build_filename_search(monkeypatch):
    import serpapi_amazon_test

    class FakeDate:
        @staticmethod
        def today():
            class D:
                def strftime(self, fmt):
                    return "2026-05-22"
            return D()

    monkeypatch.setattr(serpapi_amazon_test, "date", FakeDate)
    result = serpapi_amazon_test.build_filename("search", "weight-loss")
    assert result == "2026-05-22_full-api-test_search_weight-loss.csv"


def test_build_filename_product(monkeypatch):
    import serpapi_amazon_test

    class FakeDate:
        @staticmethod
        def today():
            class D:
                def strftime(self, fmt):
                    return "2026-05-22"
            return D()

    monkeypatch.setattr(serpapi_amazon_test, "date", FakeDate)
    result = serpapi_amazon_test.build_filename("product", "B09ABC1234")
    assert result == "2026-05-22_full-api-test_product_B09ABC1234.csv"


# ── flatten_response ─────────────────────────────────────────────────────────

def test_flatten_response_list_section():
    from serpapi_amazon_test import flatten_response
    response = {
        "organic_results": [
            {"asin": "A1", "title": "Foo"},
            {"asin": "A2", "title": "Bar"},
        ]
    }
    rows = flatten_response(response)
    assert len(rows) == 2
    assert rows[0]["section"] == "organic_results"
    assert rows[0]["item_index"] == 0
    assert json.loads(rows[0]["data"])["asin"] == "A1"
    assert rows[1]["item_index"] == 1
    assert json.loads(rows[1]["data"])["asin"] == "A2"


def test_flatten_response_dict_section():
    from serpapi_amazon_test import flatten_response
    response = {
        "search_information": {"query_displayed": "test", "total_results": 100},
    }
    rows = flatten_response(response)
    assert len(rows) == 1
    assert rows[0]["section"] == "search_information"
    assert rows[0]["item_index"] == 0
    assert json.loads(rows[0]["data"])["total_results"] == 100


def test_flatten_response_extra_cols():
    from serpapi_amazon_test import flatten_response
    response = {"product_results": {"title": "Foo"}}
    rows = flatten_response(response, extra_cols={"asin": "B09ABC"})
    assert rows[0]["asin"] == "B09ABC"
    assert rows[0]["section"] == "product_results"


def test_flatten_response_empty():
    from serpapi_amazon_test import flatten_response
    rows = flatten_response({})
    assert rows == []
