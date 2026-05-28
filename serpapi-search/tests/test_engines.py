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


# ── google_autocomplete ───────────────────────────────────────────────────────

from engines.google_autocomplete import build_params as ac_build_params, _parse_response as ac_parse

def test_autocomplete_build_params_no_location_no_pages():
    p = ac_build_params("coffee", "us", "en")
    assert p["engine"] == "google_autocomplete"
    assert p["client"] == "chrome"
    assert "location" not in p
    assert "pages" not in p

def test_autocomplete_build_params_correct_keys():
    p = ac_build_params("cof", "gb", "en")
    assert p["gl"] == "gb"
    assert p["hl"] == "en"
    assert p["q"] == "cof"

def test_autocomplete_parse_maps_suggestions():
    sug = [{"value": "coffee near me", "relevance": 1250}]
    response = {"search_metadata": {}, "search_parameters": {}, "search_information": {}, "suggestions": sug}
    sections, _ = ac_parse(response)
    assert sections["suggestions"] == sug

def test_autocomplete_parse_maps_verbatim_relevance():
    response = {"search_metadata": {}, "search_parameters": {}, "search_information": {}, "verbatim_relevance": 1337}
    sections, _ = ac_parse(response)
    assert sections["verbatim_relevance"] == 1337

def test_autocomplete_parse_strips_search_information():
    response = {"search_metadata": {}, "search_parameters": {}, "search_information": {"query": "coffee"}, "suggestions": []}
    sections, unmapped = ac_parse(response)
    assert "search_information" not in sections
    assert unmapped is None

def test_autocomplete_parse_unmapped_captured():
    response = {"search_metadata": {}, "search_parameters": {}, "search_information": {}, "unknown_section": {"x": 1}}
    _, unmapped = ac_parse(response)
    assert unmapped == {"unknown_section": {"x": 1}}


# ── google_forums ─────────────────────────────────────────────────────────────

from engines.google_forums import build_params as gf_build_params, _parse_response as gf_parse

def test_forums_build_params_required():
    p = gf_build_params("coffee reddit", "us", "en", None, 1)
    assert p["engine"] == "google_forums"
    assert p["q"] == "coffee reddit"
    assert p["pages"] == 1

def test_forums_build_params_relative_period():
    p = gf_build_params("coffee reddit", "us", "en", None, 1, period_unit="m", period_value=3)
    assert p["period_unit"] == "m"
    assert p["period_value"] == 3
    assert "start_date" not in p

def test_forums_build_params_absolute_dates():
    p = gf_build_params("coffee reddit", "us", "en", None, 1,
                        start_date="20250101", end_date="20251231")
    assert p["start_date"] == "20250101"
    assert p["end_date"] == "20251231"
    assert "period_unit" not in p

def test_forums_build_params_period_and_date_mutually_exclusive():
    p = gf_build_params("coffee reddit", "us", "en", None, 1,
                        period_unit="d", period_value=7,
                        start_date="20250101")
    assert "period_unit" in p
    assert "start_date" not in p

def test_forums_parse_maps_organic_results():
    results = [{"title": "Post 1", "link": "https://reddit.com/r/coffee"}]
    response = {"search_metadata": {}, "search_parameters": {}, "organic_results": results}
    sections, _ = gf_parse(response)
    assert sections["organic_results"] == results

def test_forums_parse_unmapped_captured():
    response = {"search_metadata": {}, "search_parameters": {}, "extra": {"k": "v"}}
    _, unmapped = gf_parse(response)
    assert unmapped == {"extra": {"k": "v"}}


# ── google_jobs ───────────────────────────────────────────────────────────────

from engines.google_jobs import build_params as gj_build_params, _parse_response as gj_parse

def test_jobs_build_params_required():
    p = gj_build_params("software engineer", "us", "en", None, 2)
    assert p["engine"] == "google_jobs"
    assert p["q"] == "software engineer"
    assert p["pages"] == 2

def test_jobs_build_params_lrad():
    p = gj_build_params("software engineer", "us", "en", None, 1, lrad=50)
    assert p["lrad"] == 50

def test_jobs_build_params_lrad_omitted_when_none():
    p = gj_build_params("software engineer", "us", "en", None, 1)
    assert "lrad" not in p

def test_jobs_build_params_with_location():
    p = gj_build_params("software engineer", "us", "en", "Austin, Texas", 1)
    assert p["location"] == "Austin, Texas"

def test_jobs_parse_maps_jobs_results():
    jobs = [{"title": "Engineer", "company_name": "Acme"}]
    response = {"search_metadata": {}, "search_parameters": {}, "jobs_results": jobs}
    sections, _ = gj_parse(response)
    assert sections["jobs_results"] == jobs

def test_jobs_parse_unmapped_captured():
    response = {"search_metadata": {}, "search_parameters": {}, "new_section": {"x": 1}}
    _, unmapped = gj_parse(response)
    assert unmapped == {"new_section": {"x": 1}}
