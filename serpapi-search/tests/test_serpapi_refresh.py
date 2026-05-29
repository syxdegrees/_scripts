"""Tests for serpapi_refresh.py utilities."""
import csv as csv_module
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from serpapi_refresh import (  # noqa: E402
    EXTRA_PARAMS,
    PHRASES,
    build_field_table,
    engine_to_slug,
    flatten_value,
    write_csv,
    write_ref_doc,
)


# --- engine_to_slug ---

def test_engine_to_slug_no_underscores():
    assert engine_to_slug("google") == "google"


def test_engine_to_slug_single_underscore():
    assert engine_to_slug("google_light") == "google-light"


def test_engine_to_slug_multiple_underscores():
    assert engine_to_slug("google_ai_mode") == "google-ai-mode"


# --- PHRASES ---

def test_phrases_google_is_coffee():
    assert PHRASES["google"] == "coffee"


def test_phrases_finance_is_ticker():
    assert PHRASES["google_finance"] == "AAPL:NASDAQ"


def test_phrases_amazon_is_coffee_maker():
    assert PHRASES["amazon"] == "coffee maker"


def test_phrases_jobs_is_barista():
    assert PHRASES["google_jobs"] == "barista"


def test_phrases_play_games_is_puzzle():
    assert PHRASES["google_play_games"] == "puzzle"


def test_phrases_play_movies_is_comedy():
    assert PHRASES["google_play_movies"] == "comedy"


# --- EXTRA_PARAMS ---

def test_extra_params_google_maps_has_type_and_ll():
    assert EXTRA_PARAMS["google_maps"]["type"] == "search"
    assert "ll" in EXTRA_PARAMS["google_maps"]


def test_extra_params_google_trends_has_data_type():
    assert EXTRA_PARAMS["google_trends"]["data_type"] == "TIMESERIES"


# --- flatten_value ---

def test_flatten_value_flat_dict():
    result = flatten_value({"title": "Best Coffee", "link": "https://example.com"})
    assert result == {"title": "Best Coffee", "link": "https://example.com"}


def test_flatten_value_nested_dict():
    result = flatten_value({"metadata": {"id": "abc", "status": "ok"}})
    assert result == {"metadata.id": "abc", "metadata.status": "ok"}


def test_flatten_value_with_list():
    result = flatten_value({"items": ["a", "b"]})
    assert result == {"items.0": "a", "items.1": "b"}


def test_flatten_value_none():
    result = flatten_value({"key": None})
    assert result == {"key": None}


def test_flatten_value_scalar_string():
    result = flatten_value("hello", prefix="field")
    assert result == {"field": "hello"}


# --- build_field_table ---

def test_build_field_table_flat_fields():
    data = {"status": "Success", "count": 10}
    rows = build_field_table(data)
    paths = [r["path"] for r in rows]
    assert "status" in paths
    assert "count" in paths


def test_build_field_table_nested_dict():
    data = {"metadata": {"id": "abc"}}
    rows = build_field_table(data)
    paths = [r["path"] for r in rows]
    assert "metadata.id" in paths


def test_build_field_table_array_of_objects():
    data = {"results": [{"title": "A", "link": "https://a.com"}]}
    rows = build_field_table(data)
    paths = [r["path"] for r in rows]
    assert "results[]" in paths
    assert "results[].title" in paths
    assert "results[].link" in paths


def test_build_field_table_empty_array():
    data = {"results": []}
    rows = build_field_table(data)
    assert any(r["path"] == "results[]" for r in rows)
    assert any(r["example"] == "(empty)" for r in rows)


def test_build_field_table_array_of_scalars():
    data = {"tags": ["coffee", "hot"]}
    rows = build_field_table(data)
    assert any(r["path"] == "tags[]" for r in rows)
    assert any("array of" in r["type"] for r in rows)


def test_build_field_table_example_truncated():
    data = {"long_field": "x" * 200}
    rows = build_field_table(data)
    assert len(rows[0]["example"]) <= 80


# --- write_ref_doc ---

def test_write_ref_doc_creates_file(tmp_path):
    data = {
        "search_metadata": {"id": "abc123", "status": "Success"},
        "organic_results": [{"title": "Best Coffee", "link": "https://example.com"}],
    }
    write_ref_doc(tmp_path, "google", "2026-05-29", data)
    doc = tmp_path / "_ref" / "serpapi-search-reference-google.md"
    assert doc.exists()


def test_write_ref_doc_contains_date(tmp_path):
    data = {"search_metadata": {"status": "Success"}}
    write_ref_doc(tmp_path, "google", "2026-05-29", data)
    content = (tmp_path / "_ref" / "serpapi-search-reference-google.md").read_text(encoding="utf-8")
    assert "2026-05-29" in content


def test_write_ref_doc_contains_field_paths(tmp_path):
    data = {"organic_results": [{"title": "Best Coffee", "link": "https://example.com"}]}
    write_ref_doc(tmp_path, "google", "2026-05-29", data)
    content = (tmp_path / "_ref" / "serpapi-search-reference-google.md").read_text(encoding="utf-8")
    assert "organic_results[].title" in content
    assert "organic_results[].link" in content


def test_write_ref_doc_slug_conversion(tmp_path):
    data = {"search_metadata": {"status": "Success"}}
    write_ref_doc(tmp_path, "google_light", "2026-05-29", data)
    doc = tmp_path / "_ref" / "serpapi-search-reference-google-light.md"
    assert doc.exists()


def test_write_ref_doc_error_response(tmp_path):
    data = {"error": "Invalid API key"}
    write_ref_doc(tmp_path, "google", "2026-05-29", data)
    content = (tmp_path / "_ref" / "serpapi-search-reference-google.md").read_text(encoding="utf-8")
    assert "ERROR" in content
    assert "Invalid API key" in content


def test_write_ref_doc_creates_ref_dir(tmp_path):
    write_ref_doc(tmp_path, "amazon", "2026-05-29", {"status": "ok"})
    assert (tmp_path / "_ref").is_dir()


# --- write_csv ---

def test_write_csv_creates_file(tmp_path):
    data = {"organic_results": [{"title": "A", "link": "https://a.com"}]}
    write_csv(tmp_path, "google", "2026-05-29", data)
    csv_path = tmp_path / "_ref" / "data" / "2026-05-29-serpapi-search-reference-google-data.csv"
    assert csv_path.exists()


def test_write_csv_section_and_index_columns(tmp_path):
    data = {"organic_results": [{"title": "A"}]}
    write_csv(tmp_path, "google", "2026-05-29", data)
    csv_path = tmp_path / "_ref" / "data" / "2026-05-29-serpapi-search-reference-google-data.csv"
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv_module.DictReader(f))
    assert rows[0]["_section"] == "organic_results"
    assert rows[0]["_index"] == "0"


def test_write_csv_empty_data_writes_headers(tmp_path):
    write_csv(tmp_path, "google", "2026-05-29", {})
    csv_path = tmp_path / "_ref" / "data" / "2026-05-29-serpapi-search-reference-google-data.csv"
    content = csv_path.read_text(encoding="utf-8")
    assert "_section" in content
    assert "_index" in content


def test_write_csv_slug_in_filename(tmp_path):
    write_csv(tmp_path, "google_light", "2026-05-29", {"results": [{"title": "x"}]})
    csv_path = tmp_path / "_ref" / "data" / "2026-05-29-serpapi-search-reference-google-light-data.csv"
    assert csv_path.exists()


def test_write_csv_creates_data_dir(tmp_path):
    write_csv(tmp_path, "google", "2026-05-29", {})
    assert (tmp_path / "_ref" / "data").is_dir()


def test_write_csv_multiple_sections(tmp_path):
    data = {
        "organic_results": [{"title": "A"}],
        "ads": [{"title": "Ad1"}],
    }
    write_csv(tmp_path, "google", "2026-05-29", data)
    csv_path = tmp_path / "_ref" / "data" / "2026-05-29-serpapi-search-reference-google-data.csv"
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv_module.DictReader(f))
    sections = {r["_section"] for r in rows}
    assert "organic_results" in sections
    assert "ads" in sections
