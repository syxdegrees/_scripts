"""Tests for mapping helper functions in serpapi_amazon_search.py."""
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from serpapi_amazon_search import (
    load_mapping,
    extract_field,
    build_mapped_search_row,
    build_mapped_product_row,
    build_row_from_mapping,
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


# ── build_mapped_search_row ──────────────────────────────────────────────────

def test_build_mapped_search_row_extracts_fields():
    item = {"asin": "B000NKI0V8", "title": "Test Product", "price": "$17.85", "rating": 4.4}
    table_mapping = {"table": "products", "fields": [
        {"source_section": "organic_results", "source_field": "asin",  "dest_column": "asin"},
        {"source_section": "organic_results", "source_field": "title", "dest_column": "product_title"},
        {"source_section": "organic_results", "source_field": "price", "dest_column": "price"},
    ]}
    row = build_mapped_search_row(item, table_mapping)
    assert row == {"asin": "B000NKI0V8", "product_title": "Test Product", "price": "$17.85"}

def test_build_mapped_search_row_missing_field_is_none():
    item = {"asin": "B000NKI0V8"}
    table_mapping = {"table": "products", "fields": [
        {"source_section": "organic_results", "source_field": "asin",  "dest_column": "asin"},
        {"source_section": "organic_results", "source_field": "price", "dest_column": "price"},
    ]}
    row = build_mapped_search_row(item, table_mapping)
    assert row["asin"] == "B000NKI0V8"
    assert row["price"] is None

def test_build_mapped_search_row_nested_field():
    item = {"rating": 4.4, "offers": {"savings": "$3.00"}}
    table_mapping = {"table": "t", "fields": [
        {"source_section": "s", "source_field": "offers.savings", "dest_column": "savings"},
    ]}
    row = build_mapped_search_row(item, table_mapping)
    assert row["savings"] == "$3.00"


# ── build_mapped_product_row ─────────────────────────────────────────────────

def test_build_mapped_product_row_simple_field():
    product_response = {
        "product_results": {"title": "Test Product", "price": "$17.85"},
    }
    table_mapping = {"table": "products", "fields": [
        {"source_section": "product_results", "source_field": "title", "dest_column": "product_title", "phase": "product"},
        {"source_section": "product_results", "source_field": "price", "dest_column": "price",         "phase": "product"},
    ]}
    row = build_mapped_product_row(product_response, table_mapping)
    assert row["product_title"] == "Test Product"
    assert row["price"] == "$17.85"

def test_build_mapped_product_row_array_section_stored_as_list():
    product_response = {
        "about_item": ["Feature 1", "Feature 2", "Feature 3"],
    }
    table_mapping = {"table": "products", "fields": [
        {"source_section": "about_item", "source_field": "items", "dest_column": "bullets", "phase": "product"},
    ]}
    row = build_mapped_product_row(product_response, table_mapping)
    assert row["bullets"] == ["Feature 1", "Feature 2", "Feature 3"]

def test_build_mapped_product_row_nested_field():
    product_response = {
        "reviews_information": {"summary": {"text": "Great product overall."}},
    }
    table_mapping = {"table": "products", "fields": [
        {"source_section": "reviews_information", "source_field": "summary.text", "dest_column": "ai_summary", "phase": "product"},
    ]}
    row = build_mapped_product_row(product_response, table_mapping)
    assert row["ai_summary"] == "Great product overall."

def test_build_mapped_product_row_missing_section_is_none():
    product_response = {}
    table_mapping = {"table": "t", "fields": [
        {"source_section": "product_results", "source_field": "title", "dest_column": "title", "phase": "product"},
    ]}
    row = build_mapped_product_row(product_response, table_mapping)
    assert row["title"] is None


# ── build_row_from_mapping ───────────────────────────────────────────────────

def test_build_row_from_mapping_merges_phases():
    search_item = {"asin": "B000NKI0V8", "title": "Search Title", "price": "$17.85"}
    product_response = {
        "product_results": {"title": "Product Title", "rating": 4.4},
        "about_item": ["Feature 1"],
    }
    table_mapping = {"table": "products", "fields": [
        {"source_section": "organic_results", "source_field": "asin",   "dest_column": "asin",          "phase": "search"},
        {"source_section": "organic_results", "source_field": "title",  "dest_column": "search_title",  "phase": "search"},
        {"source_section": "organic_results", "source_field": "price",  "dest_column": "search_price",  "phase": "search"},
        {"source_section": "product_results", "source_field": "title",  "dest_column": "product_title", "phase": "product"},
        {"source_section": "product_results", "source_field": "rating", "dest_column": "rating",        "phase": "product"},
        {"source_section": "about_item",      "source_field": "items",  "dest_column": "bullets",       "phase": "product"},
    ]}
    row = build_row_from_mapping(search_item, product_response, table_mapping)
    assert row["asin"] == "B000NKI0V8"
    assert row["search_title"] == "Search Title"
    assert row["search_price"] == "$17.85"
    assert row["product_title"] == "Product Title"
    assert row["rating"] == 4.4
    assert row["bullets"] == ["Feature 1"]

def test_build_row_from_mapping_missing_search_field_is_none():
    search_item = {"asin": "B1"}
    product_response = {}
    table_mapping = {"table": "t", "fields": [
        {"source_section": "organic_results", "source_field": "price", "dest_column": "price", "phase": "search"},
    ]}
    row = build_row_from_mapping(search_item, product_response, table_mapping)
    assert row["price"] is None

def test_build_row_from_mapping_missing_product_section_is_none():
    search_item = {}
    product_response = {}
    table_mapping = {"table": "t", "fields": [
        {"source_section": "product_results", "source_field": "rating", "dest_column": "rating", "phase": "product"},
    ]}
    row = build_row_from_mapping(search_item, product_response, table_mapping)
    assert row["rating"] is None
