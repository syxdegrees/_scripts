"""Tests for mapping helper functions in serpapi_amazon_search.py."""
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from serpapi_amazon_search import (
    load_mapping,
    extract_field,
    navigate_path,
    build_rows_from_mapping,
)


# ── extract_field ────────────────────────────────────────────────────────────

def test_extract_field_simple():
    assert extract_field({"asin": "B000NKI0V8"}, "asin") == "B000NKI0V8"

def test_extract_field_nested():
    obj = {"summary": {"text": "Great product"}}
    assert extract_field(obj, "summary.text") == "Great product"

def test_extract_field_deeply_nested():
    obj = {"a": {"b": {"c": 42}}}
    assert extract_field(obj, "a.b.c") == 42

def test_extract_field_missing_key_returns_none():
    assert extract_field({"asin": "B1"}, "price") is None

def test_extract_field_missing_nested_returns_none():
    obj = {"summary": {"text": "hi"}}
    assert extract_field(obj, "summary.missing") is None

def test_extract_field_none_obj_returns_none():
    assert extract_field(None, "asin") is None

def test_extract_field_non_dict_returns_none():
    assert extract_field("not a dict", "asin") is None

def test_extract_field_intermediate_none():
    obj = {"a": None}
    assert extract_field(obj, "a.b") is None


# ── load_mapping ─────────────────────────────────────────────────────────────

def test_load_mapping_valid_list(tmp_path):
    mapping = [{"table": "products", "fields": [
        {"source_section": "organic_results", "source_field": "asin", "dest_column": "asin"}
    ]}]
    f = tmp_path / "mapping.json"
    f.write_text(json.dumps(mapping))
    result = load_mapping(str(f))
    assert len(result) == 1
    assert result[0]["table"] == "products"
    assert result[0]["fields"][0]["dest_column"] == "asin"

def test_load_mapping_single_dict_wrapped_in_list(tmp_path):
    mapping = {"table": "products", "fields": [
        {"source_section": "organic_results", "source_field": "asin", "dest_column": "asin"}
    ]}
    f = tmp_path / "mapping.json"
    f.write_text(json.dumps(mapping))
    result = load_mapping(str(f))
    assert isinstance(result, list)
    assert len(result) == 1

def test_load_mapping_valid_phase(tmp_path):
    mapping = [{"table": "t", "fields": [
        {"source_section": "s", "source_field": "f", "dest_column": "c", "phase": "search"},
        {"source_section": "s", "source_field": "f", "dest_column": "d", "phase": "product"},
    ]}]
    f = tmp_path / "mapping.json"
    f.write_text(json.dumps(mapping))
    result = load_mapping(str(f))
    assert len(result[0]["fields"]) == 2

def test_load_mapping_missing_table_exits(tmp_path):
    mapping = [{"fields": [{"source_section": "x", "source_field": "y", "dest_column": "z"}]}]
    f = tmp_path / "mapping.json"
    f.write_text(json.dumps(mapping))
    with pytest.raises(SystemExit):
        load_mapping(str(f))

def test_load_mapping_missing_fields_exits(tmp_path):
    mapping = [{"table": "t"}]
    f = tmp_path / "mapping.json"
    f.write_text(json.dumps(mapping))
    with pytest.raises(SystemExit):
        load_mapping(str(f))

def test_load_mapping_invalid_phase_exits(tmp_path):
    mapping = [{"table": "t", "fields": [
        {"source_section": "s", "source_field": "f", "dest_column": "c", "phase": "bad"}
    ]}]
    f = tmp_path / "mapping.json"
    f.write_text(json.dumps(mapping))
    with pytest.raises(SystemExit):
        load_mapping(str(f))

def test_load_mapping_file_not_found_exits():
    with pytest.raises(SystemExit):
        load_mapping("/nonexistent/path/mapping.json")

def test_load_mapping_invalid_json_exits(tmp_path):
    f = tmp_path / "mapping.json"
    f.write_text("this is not json {{{")
    with pytest.raises(SystemExit):
        load_mapping(str(f))

def test_load_mapping_null_row_source_is_valid(tmp_path):
    mapping = [{"table": "t", "row_source": None, "fields": [
        {"source_section": "s", "source_field": "f", "dest_column": "c"}
    ]}]
    f = tmp_path / "m.json"
    f.write_text(json.dumps(mapping))
    result = load_mapping(str(f))
    assert result[0]["row_source"] is None

def test_load_mapping_valid_dot_path_row_source(tmp_path):
    mapping = [{"table": "t", "row_source": "reviews_information.authors_reviews", "fields": [
        {"source_section": "s", "source_field": "f", "dest_column": "c"}
    ]}]
    f = tmp_path / "m.json"
    f.write_text(json.dumps(mapping))
    result = load_mapping(str(f))
    assert result[0]["row_source"] == "reviews_information.authors_reviews"

def test_load_mapping_row_source_no_dot_exits(tmp_path):
    mapping = [{"table": "t", "row_source": "organic_results", "fields": [
        {"source_section": "s", "source_field": "f", "dest_column": "c"}
    ]}]
    f = tmp_path / "m.json"
    f.write_text(json.dumps(mapping))
    with pytest.raises(SystemExit):
        load_mapping(str(f))

def test_load_mapping_row_source_empty_string_exits(tmp_path):
    mapping = [{"table": "t", "row_source": "", "fields": [
        {"source_section": "s", "source_field": "f", "dest_column": "c"}
    ]}]
    f = tmp_path / "m.json"
    f.write_text(json.dumps(mapping))
    with pytest.raises(SystemExit):
        load_mapping(str(f))


# ── navigate_path ─────────────────────────────────────────────────────────────

def test_navigate_path_single_level_list():
    obj = {
        "authors_reviews": [
            {"title": "Great", "rating": 5},
            {"title": "OK", "rating": 3},
        ]
    }
    results = navigate_path(obj, "authors_reviews")
    assert len(results) == 2
    leaf0, ctx0 = results[0]
    assert leaf0["title"] == "Great"
    assert ctx0 == {}
    leaf1, ctx1 = results[1]
    assert leaf1["title"] == "OK"
    assert ctx1 == {}


def test_navigate_path_nested_list_carries_ancestor_ctx():
    obj = {
        "summary": {
            "text": "Overall good",
            "insights": [
                {
                    "title": "Value",
                    "sentiment": "positive",
                    "examples": [
                        {"snippet": "Great value", "link": "http://a.com"},
                        {"snippet": "Worth it",    "link": "http://b.com"},
                    ],
                },
                {
                    "title": "Durability",
                    "sentiment": "negative",
                    "examples": [
                        {"snippet": "Broke fast", "link": "http://c.com"},
                    ],
                },
            ],
        }
    }
    results = navigate_path(obj, "summary.insights.examples")
    assert len(results) == 3

    leaf0, ctx0 = results[0]
    assert leaf0["snippet"] == "Great value"
    assert ctx0["summary.insights.title"]     == "Value"
    assert ctx0["summary.insights.sentiment"] == "positive"
    assert ctx0["summary.text"] == "Overall good"  # captured at summary→insights boundary

    leaf1, ctx1 = results[1]
    assert leaf1["snippet"] == "Worth it"
    assert ctx1["summary.insights.title"] == "Value"

    leaf2, ctx2 = results[2]
    assert leaf2["snippet"] == "Broke fast"
    assert ctx2["summary.insights.title"] == "Durability"


def test_navigate_path_intermediate_list_captures_scalars():
    obj = {
        "summary": {
            "text": "Overall good",
            "rating": 4.2,
            "insights": [
                {"title": "Value", "count": 10},
            ],
        }
    }
    results = navigate_path(obj, "summary.insights")
    assert len(results) == 1
    leaf, ctx = results[0]
    assert leaf["title"] == "Value"
    assert ctx["summary.text"]   == "Overall good"
    assert ctx["summary.rating"] == 4.2


def test_navigate_path_missing_key_returns_empty():
    obj = {"other": "data"}
    results = navigate_path(obj, "authors_reviews")
    assert results == []


def test_navigate_path_empty_list_returns_empty():
    obj = {"reviews": []}
    results = navigate_path(obj, "reviews")
    assert results == []


def test_navigate_path_deep_missing_path_returns_empty():
    obj = {"summary": {"text": "hi"}}
    results = navigate_path(obj, "summary.insights.examples")
    assert results == []


def test_navigate_path_non_dict_obj_returns_empty():
    results = navigate_path(None, "authors_reviews")
    assert results == []


def test_navigate_path_independent_ancestor_ctxs():
    obj = {
        "insights": [
            {"title": "A", "examples": [{"snippet": "x"}]},
            {"title": "B", "examples": [{"snippet": "y"}]},
        ]
    }
    results = navigate_path(obj, "insights.examples")
    ctxs = [ctx for _, ctx in results]
    assert ctxs[0]["insights.title"] == "A"
    assert ctxs[1]["insights.title"] == "B"


# ── build_rows_from_mapping ──────────────────────────────────────────────────

def test_build_rows_scalar_mode_product_field():
    product_response = {
        "product_results": {"title": "Test Product", "rating": 4.4},
    }
    table_mapping = {
        "table": "products",
        "row_source": None,
        "fields": [
            {"source_section": "product_results", "source_field": "title",  "dest_column": "product_title", "phase": "product"},
            {"source_section": "product_results", "source_field": "rating", "dest_column": "rating",        "phase": "product"},
        ],
    }
    rows = build_rows_from_mapping({}, product_response, table_mapping)
    assert len(rows) == 1
    assert rows[0]["product_title"] == "Test Product"
    assert rows[0]["rating"] == 4.4


def test_build_rows_scalar_mode_search_phase():
    search_item = {"asin": "B000NKI0V8", "title": "Search Title"}
    table_mapping = {
        "table": "t",
        "row_source": None,
        "fields": [
            {"source_section": "organic_results", "source_field": "asin",  "dest_column": "asin",  "phase": "search"},
            {"source_section": "organic_results", "source_field": "title", "dest_column": "title", "phase": "search"},
        ],
    }
    rows = build_rows_from_mapping(search_item, {}, table_mapping)
    assert len(rows) == 1
    assert rows[0]["asin"] == "B000NKI0V8"
    assert rows[0]["title"] == "Search Title"


def test_build_rows_scalar_mode_missing_section_is_none():
    table_mapping = {
        "table": "t",
        "row_source": None,
        "fields": [
            {"source_section": "product_results", "source_field": "title", "dest_column": "title", "phase": "product"},
        ],
    }
    rows = build_rows_from_mapping({}, {}, table_mapping)
    assert rows[0]["title"] is None


def test_build_rows_list_mode_authors_reviews():
    search_item = {"asin": "B000NKI0V8"}
    product_response = {
        "reviews_information": {
            "authors_reviews": [
                {"title": "Great", "rating": 5, "text": "Love it"},
                {"title": "OK",    "rating": 3, "text": "Works fine"},
            ]
        }
    }
    table_mapping = {
        "table": "reviews",
        "row_source": "reviews_information.authors_reviews",
        "fields": [
            {"source_section": "organic_results",     "source_field": "asin",                   "dest_column": "asin",         "phase": "search"},
            {"source_section": "reviews_information", "source_field": "authors_reviews.title",  "dest_column": "review_title", "phase": "product"},
            {"source_section": "reviews_information", "source_field": "authors_reviews.rating", "dest_column": "rating",       "phase": "product"},
        ],
    }
    rows = build_rows_from_mapping(search_item, product_response, table_mapping)
    assert len(rows) == 2
    assert rows[0]["asin"] == "B000NKI0V8"
    assert rows[0]["review_title"] == "Great"
    assert rows[0]["rating"] == 5
    assert rows[1]["asin"] == "B000NKI0V8"
    assert rows[1]["review_title"] == "OK"
    assert rows[1]["rating"] == 3


def test_build_rows_list_mode_nested_examples():
    product_response = {
        "reviews_information": {
            "summary": {
                "insights": [
                    {
                        "title": "Value",
                        "sentiment": "positive",
                        "examples": [
                            {"snippet": "Great value", "link": "http://a.com"},
                            {"snippet": "Worth it",    "link": "http://b.com"},
                        ],
                    },
                    {
                        "title": "Durability",
                        "sentiment": "negative",
                        "examples": [
                            {"snippet": "Broke fast", "link": "http://c.com"},
                        ],
                    },
                ]
            }
        }
    }
    table_mapping = {
        "table": "snippets",
        "row_source": "reviews_information.summary.insights.examples",
        "fields": [
            {"source_section": "reviews_information", "source_field": "summary.insights.title",            "dest_column": "insight_title", "phase": "product"},
            {"source_section": "reviews_information", "source_field": "summary.insights.examples.snippet", "dest_column": "snippet",       "phase": "product"},
        ],
    }
    rows = build_rows_from_mapping({}, product_response, table_mapping)
    assert len(rows) == 3
    assert rows[0]["snippet"] == "Great value"
    assert rows[0]["insight_title"] == "Value"
    assert rows[1]["snippet"] == "Worth it"
    assert rows[1]["insight_title"] == "Value"
    assert rows[2]["snippet"] == "Broke fast"
    assert rows[2]["insight_title"] == "Durability"


def test_build_rows_list_mode_empty_list_returns_empty():
    product_response = {"reviews_information": {"authors_reviews": []}}
    table_mapping = {
        "table": "t",
        "row_source": "reviews_information.authors_reviews",
        "fields": [
            {"source_section": "reviews_information", "source_field": "authors_reviews.title", "dest_column": "title", "phase": "product"},
        ],
    }
    rows = build_rows_from_mapping({}, product_response, table_mapping)
    assert rows == []


def test_build_rows_list_mode_missing_section_returns_empty():
    product_response = {}
    table_mapping = {
        "table": "t",
        "row_source": "reviews_information.authors_reviews",
        "fields": [
            {"source_section": "reviews_information", "source_field": "authors_reviews.title", "dest_column": "title", "phase": "product"},
        ],
    }
    rows = build_rows_from_mapping({}, product_response, table_mapping)
    assert rows == []


def test_build_rows_list_mode_search_field_duplicated_across_all_rows():
    search_item = {"asin": "B1"}
    product_response = {
        "reviews_information": {
            "authors_reviews": [{"title": "A"}, {"title": "B"}, {"title": "C"}]
        }
    }
    table_mapping = {
        "table": "t",
        "row_source": "reviews_information.authors_reviews",
        "fields": [
            {"source_section": "organic_results",     "source_field": "asin",                  "dest_column": "asin",  "phase": "search"},
            {"source_section": "reviews_information", "source_field": "authors_reviews.title", "dest_column": "title", "phase": "product"},
        ],
    }
    rows = build_rows_from_mapping(search_item, product_response, table_mapping)
    assert len(rows) == 3
    assert all(r["asin"] == "B1" for r in rows)
