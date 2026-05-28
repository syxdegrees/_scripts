import json
import pytest
from unittest.mock import patch, MagicMock
from engines.google_light import build_params, _parse_response, SECTION_COLS, run

# ── google_light: build_params ────────────────────────────────────────────────

def test_light_build_params_required():
    p = build_params("coffee", "us", "en", None, 1)
    assert p["engine"] == "google_light"
    assert p["q"] == "coffee"
    assert p["gl"] == "us"
    assert p["hl"] == "en"
    assert p["pages"] == 1

def test_light_build_params_with_location():
    p = build_params("coffee", "us", "en", "Austin, Texas", 1)
    assert p["location"] == "Austin, Texas"

def test_light_build_params_no_location_omits_key():
    p = build_params("coffee", "us", "en", None, 1)
    assert "location" not in p

def test_light_build_params_safe_omitted_when_none():
    p = build_params("coffee", "us", "en", None, 1, safe=None)
    assert "safe" not in p

def test_light_build_params_safe_included_when_set():
    p = build_params("coffee", "us", "en", None, 1, safe="active")
    assert p["safe"] == "active"

def test_light_build_params_defaults():
    p = build_params("coffee", "us", "en", None, 1)
    assert p["nfpr"] == 0
    assert p["filter"] == 1

# ── google_light: _parse_response ─────────────────────────────────────────────

def test_light_parse_strips_metadata():
    response = {
        "search_metadata": {"id": "abc"},
        "search_parameters": {"engine": "google_light"},
        "organic_results": [{"title": "Coffee"}],
    }
    sections, unmapped = _parse_response(response)
    assert "search_metadata" not in sections
    assert "search_parameters" not in sections

def test_light_parse_maps_known_section():
    results = [{"title": "Coffee"}]
    response = {"organic_results": results, "search_metadata": {}, "search_parameters": {}}
    sections, unmapped = _parse_response(response)
    assert sections["organic_results"] == results

def test_light_parse_unmapped_section_captured():
    response = {
        "search_metadata": {},
        "search_parameters": {},
        "some_new_section": {"data": 1},
    }
    sections, unmapped = _parse_response(response)
    assert unmapped == {"some_new_section": {"data": 1}}

def test_light_parse_unmapped_is_none_when_all_known():
    response = {
        "search_metadata": {},
        "search_parameters": {},
        "organic_results": [],
    }
    _, unmapped = _parse_response(response)
    assert unmapped is None


# ── google_ai_mode ────────────────────────────────────────────────────────────

from engines.google_ai_mode import build_params as ai_build_params, _parse_response as ai_parse

def test_ai_mode_build_params_no_pagination():
    p = ai_build_params("what is coffee", "us", "en", None)
    assert p["engine"] == "google_ai_mode"
    assert p["continuable"] is False
    assert "pages" not in p

def test_ai_mode_build_params_with_location():
    p = ai_build_params("what is coffee", "us", "en", "Austin, Texas")
    assert p["location"] == "Austin, Texas"

def test_ai_mode_build_params_no_location_omits_key():
    p = ai_build_params("what is coffee", "us", "en", None)
    assert "location" not in p

def test_ai_mode_parse_strips_metadata():
    response = {"search_metadata": {}, "search_parameters": {}, "text_blocks": [{"type": "paragraph", "snippet": "..."}]}
    sections, _ = ai_parse(response)
    assert "search_metadata" not in sections

def test_ai_mode_parse_maps_text_blocks():
    payload = [{"type": "paragraph", "snippet": "Coffee is a beverage."}]
    response = {"search_metadata": {}, "search_parameters": {}, "text_blocks": payload}
    sections, _ = ai_parse(response)
    assert sections["text_blocks"] == payload

def test_ai_mode_parse_maps_references():
    refs = [{"index": 1, "title": "Wikipedia", "link": "https://en.wikipedia.org"}]
    response = {"search_metadata": {}, "search_parameters": {}, "references": refs}
    sections, _ = ai_parse(response)
    assert sections["references"] == refs
