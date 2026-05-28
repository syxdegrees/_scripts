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


# ── google_local ──────────────────────────────────────────────────────────────

from engines.google_local import build_params as gl_build_params, _parse_response as gl_parse

def test_local_build_params_required():
    p = gl_build_params("coffee", "us", "en", None, 1)
    assert p["engine"] == "google_local"
    assert p["q"] == "coffee"
    assert p["gl"] == "us"
    assert p["hl"] == "en"
    assert p["pages"] == 1

def test_local_build_params_with_location():
    p = gl_build_params("coffee", "us", "en", "Austin, Texas", 1)
    assert p["location"] == "Austin, Texas"

def test_local_build_params_no_location_omits_key():
    p = gl_build_params("coffee", "us", "en", None, 1)
    assert "location" not in p

def test_local_parse_strips_metadata():
    response = {"search_metadata": {}, "search_parameters": {}, "local_results": []}
    sections, _ = gl_parse(response)
    assert "search_metadata" not in sections

def test_local_parse_maps_local_results():
    results = [{"title": "Cafe One"}]
    response = {"search_metadata": {}, "search_parameters": {}, "local_results": results}
    sections, _ = gl_parse(response)
    assert sections["local_results"] == results

def test_local_parse_unmapped_captured():
    response = {"search_metadata": {}, "search_parameters": {}, "extra": {"x": 1}}
    _, unmapped = gl_parse(response)
    assert unmapped == {"extra": {"x": 1}}


# ── google_maps ───────────────────────────────────────────────────────────────

from engines.google_maps import build_params as gm_build_params, _parse_response as gm_parse

def test_maps_build_params_type_search_hardcoded():
    p = gm_build_params("coffee", "us", "en", None, 1)
    assert p["engine"] == "google_maps"
    assert p["type"] == "search"

def test_maps_build_params_with_ll():
    p = gm_build_params("coffee", "us", "en", None, 1, ll="@40.7455096,-74.0083012,14z")
    assert p["ll"] == "@40.7455096,-74.0083012,14z"

def test_maps_build_params_ll_omitted_when_none():
    p = gm_build_params("coffee", "us", "en", None, 1)
    assert "ll" not in p

def test_maps_parse_maps_local_results():
    results = [{"title": "Cafe"}]
    response = {"search_metadata": {}, "search_parameters": {}, "local_results": results}
    sections, _ = gm_parse(response)
    assert sections["local_results"] == results

def test_maps_parse_unmapped_captured():
    response = {"search_metadata": {}, "search_parameters": {}, "new_key": {"x": 1}}
    _, unmapped = gm_parse(response)
    assert unmapped == {"new_key": {"x": 1}}


# ── google_maps_autocomplete ──────────────────────────────────────────────────

from engines.google_maps_autocomplete import build_params as gma_build_params, _parse_response as gma_parse

def test_maps_autocomplete_build_params_no_location_no_pages():
    p = gma_build_params("cafe", "us", "en")
    assert p["engine"] == "google_maps_autocomplete"
    assert "location" not in p
    assert "pages" not in p

def test_maps_autocomplete_build_params_gl_hl():
    p = gma_build_params("cafe", "gb", "en")
    assert p["gl"] == "gb"
    assert p["hl"] == "en"

def test_maps_autocomplete_parse_maps_suggestions():
    sug = [{"value": "cafe near me"}]
    response = {"search_metadata": {}, "search_parameters": {}, "search_information": {}, "suggestions": sug}
    sections, _ = gma_parse(response)
    assert sections["suggestions"] == sug

def test_maps_autocomplete_parse_strips_search_information():
    response = {"search_metadata": {}, "search_parameters": {}, "search_information": {"q": "cafe"}, "suggestions": []}
    sections, unmapped = gma_parse(response)
    assert "search_information" not in sections
    assert unmapped is None


# ── google_news_light ─────────────────────────────────────────────────────────

from engines.google_news_light import build_params as gnl_build_params, _parse_response as gnl_parse

def test_news_build_params_required():
    p = gnl_build_params("coffee", "us", "en", None, 1)
    assert p["engine"] == "google_news_light"
    assert p["q"] == "coffee"
    assert p["pages"] == 1

def test_news_build_params_with_location():
    p = gnl_build_params("coffee", "us", "en", "Austin, Texas", 1)
    assert p["location"] == "Austin, Texas"

def test_news_build_params_no_location_omits_key():
    p = gnl_build_params("coffee", "us", "en", None, 1)
    assert "location" not in p

def test_news_parse_maps_news_results():
    results = [{"title": "Coffee News", "link": "https://example.com"}]
    response = {"search_metadata": {}, "search_parameters": {}, "news_results": results}
    sections, _ = gnl_parse(response)
    assert sections["news_results"] == results

def test_news_parse_unmapped_captured():
    response = {"search_metadata": {}, "search_parameters": {}, "extra": {"k": "v"}}
    _, unmapped = gnl_parse(response)
    assert unmapped == {"extra": {"k": "v"}}


# ── google_patents ────────────────────────────────────────────────────────────

from engines.google_patents import build_params as gp_build_params, _parse_response as gp_parse

def test_patents_build_params_required():
    p = gp_build_params("machine learning", "us", "en", None, 1)
    assert p["engine"] == "google_patents"
    assert p["q"] == "machine learning"

def test_patents_build_params_cluster_omitted_when_false():
    p = gp_build_params("ml", "us", "en", None, 1, cluster=False)
    assert "cluster" not in p

def test_patents_build_params_cluster_included_when_true():
    p = gp_build_params("ml", "us", "en", None, 1, cluster=True)
    assert p["cluster"] == "true"

def test_patents_parse_maps_organic_results():
    results = [{"title": "Patent 1", "patent_id": "US123"}]
    response = {"search_metadata": {}, "search_parameters": {}, "organic_results": results}
    sections, _ = gp_parse(response)
    assert sections["organic_results"] == results

def test_patents_parse_unmapped_captured():
    response = {"search_metadata": {}, "search_parameters": {}, "extra": {"x": 1}}
    _, unmapped = gp_parse(response)
    assert unmapped == {"extra": {"x": 1}}


# ── google_play group ─────────────────────────────────────────────────────────

from engines.google_play import build_params as gplay_build_params, _parse_response as gplay_parse
from engines.google_play_games import build_params as gpgames_build_params
from engines.google_play_movies import build_params as gpmovies_build_params
from engines.google_play_books import build_params as gpbooks_build_params

def test_play_build_params_required():
    p = gplay_build_params("fitness", "us", "en", 1)
    assert p["engine"] == "google_play"
    assert p["q"] == "fitness"
    assert p["gl"] == "us"
    assert p["hl"] == "en"
    assert p["pages"] == 1

def test_play_games_engine_name():
    p = gpgames_build_params("chess", "us", "en", 1)
    assert p["engine"] == "google_play_games"

def test_play_movies_engine_name():
    p = gpmovies_build_params("action", "us", "en", 1)
    assert p["engine"] == "google_play_movies"

def test_play_books_engine_name():
    p = gpbooks_build_params("python", "us", "en", 1)
    assert p["engine"] == "google_play_books"

def test_play_parse_maps_organic_results():
    results = [{"title": "App Section", "items": [{"product_id": "com.example"}]}]
    response = {"search_metadata": {}, "search_parameters": {}, "organic_results": results}
    sections, _ = gplay_parse(response)
    assert sections["organic_results"] == results

def test_play_parse_unmapped_captured():
    response = {"search_metadata": {}, "search_parameters": {}, "extra": {"x": 1}}
    _, unmapped = gplay_parse(response)
    assert unmapped == {"extra": {"x": 1}}


# ── google_scholar ────────────────────────────────────────────────────────────

from engines.google_scholar import build_params as gs_build_params, _parse_response as gs_parse

def test_scholar_build_params_required():
    p = gs_build_params("biology", "us", "en", None, 1)
    assert p["engine"] == "google_scholar"
    assert p["q"] == "biology"

def test_scholar_build_params_as_sdt_omitted_when_none():
    p = gs_build_params("biology", "us", "en", None, 1)
    assert "as_sdt" not in p

def test_scholar_build_params_as_sdt_included_when_set():
    p = gs_build_params("machine learning", "us", "en", None, 1, as_sdt="4")
    assert p["as_sdt"] == "4"

def test_scholar_parse_maps_organic_results():
    results = [{"title": "A Study", "link": "https://scholar.google.com"}]
    response = {"search_metadata": {}, "search_parameters": {}, "organic_results": results}
    sections, _ = gs_parse(response)
    assert sections["organic_results"] == results

def test_scholar_parse_unmapped_captured():
    response = {"search_metadata": {}, "search_parameters": {}, "extra": {"x": 1}}
    _, unmapped = gs_parse(response)
    assert unmapped == {"extra": {"x": 1}}


# ── google_shopping_light ─────────────────────────────────────────────────────

from engines.google_shopping_light import build_params as gsl_build_params, _parse_response as gsl_parse

def test_shopping_build_params_required():
    p = gsl_build_params("headphones", "us", "en", 1)
    assert p["engine"] == "google_shopping_light"
    assert p["q"] == "headphones"

def test_shopping_parse_maps_inline_shopping_results():
    results = [{"title": "Sony Headphones", "price": "$99"}]
    response = {"search_metadata": {}, "search_parameters": {}, "inline_shopping_results": results}
    sections, _ = gsl_parse(response)
    assert sections["inline_shopping_results"] == results

def test_shopping_parse_unmapped_captured():
    response = {"search_metadata": {}, "search_parameters": {}, "extra": {"x": 1}}
    _, unmapped = gsl_parse(response)
    assert unmapped == {"extra": {"x": 1}}


# ── google_videos_light ───────────────────────────────────────────────────────

from engines.google_videos_light import build_params as gvl_build_params, _parse_response as gvl_parse

def test_videos_build_params_required():
    p = gvl_build_params("coffee brewing", "us", "en", 1)
    assert p["engine"] == "google_videos_light"
    assert p["q"] == "coffee brewing"

def test_videos_parse_maps_video_results():
    results = [{"title": "Coffee Tutorial", "link": "https://youtube.com"}]
    response = {"search_metadata": {}, "search_parameters": {}, "video_results": results}
    sections, _ = gvl_parse(response)
    assert sections["video_results"] == results

def test_videos_parse_unmapped_captured():
    response = {"search_metadata": {}, "search_parameters": {}, "extra": {"x": 1}}
    _, unmapped = gvl_parse(response)
    assert unmapped == {"extra": {"x": 1}}


# ── google_short_videos ───────────────────────────────────────────────────────

from engines.google_short_videos import build_params as gsv_build_params, _parse_response as gsv_parse

def test_short_videos_build_params_no_location_no_pages():
    p = gsv_build_params("coffee", "us", "en")
    assert p["engine"] == "google_short_videos"
    assert "location" not in p
    assert "pages" not in p

def test_short_videos_parse_maps_short_video_results():
    results = [{"title": "Coffee Short", "channel": "CafeChan"}]
    response = {"search_metadata": {}, "search_parameters": {}, "short_video_results": results}
    sections, _ = gsv_parse(response)
    assert sections["short_video_results"] == results

def test_short_videos_parse_unmapped_captured():
    response = {"search_metadata": {}, "search_parameters": {}, "extra": {"x": 1}}
    _, unmapped = gsv_parse(response)
    assert unmapped == {"extra": {"x": 1}}


# ── google_trends ─────────────────────────────────────────────────────────────

from engines.google_trends import build_params as gt_build_params, _parse_response as gt_parse

def test_trends_build_params_default_data_type():
    p = gt_build_params("coffee")
    assert p["engine"] == "google_trends"
    assert p["data_type"] == "TIMESERIES"
    assert "tz" not in p

def test_trends_build_params_custom_data_type():
    p = gt_build_params("coffee", data_type="GEO_MAP_0")
    assert p["data_type"] == "GEO_MAP_0"

def test_trends_build_params_tz_included_when_set():
    p = gt_build_params("coffee", tz=-300)
    assert p["tz"] == -300

def test_trends_build_params_tz_omitted_when_none():
    p = gt_build_params("coffee")
    assert "tz" not in p

def test_trends_parse_maps_interest_over_time():
    data = {"timeline_data": [{"date": "May 2025", "values": [{"value": 75}]}]}
    response = {"search_metadata": {}, "search_parameters": {}, "interest_over_time": data}
    sections, _ = gt_parse(response)
    assert sections["interest_over_time"] == data

def test_trends_parse_maps_related_queries():
    data = {"rising": [{"query": "cold brew", "value": "Breakout"}]}
    response = {"search_metadata": {}, "search_parameters": {}, "related_queries": data}
    sections, _ = gt_parse(response)
    assert sections["related_queries"] == data

def test_trends_parse_unmapped_captured():
    response = {"search_metadata": {}, "search_parameters": {}, "extra": {"x": 1}}
    _, unmapped = gt_parse(response)
    assert unmapped == {"extra": {"x": 1}}


# ── google_trends_autocomplete ────────────────────────────────────────────────

from engines.google_trends_autocomplete import build_params as gta_build_params, _parse_response as gta_parse

def test_trends_autocomplete_build_params_only_q():
    p = gta_build_params("coffee")
    assert p["engine"] == "google_trends_autocomplete"
    assert p["q"] == "coffee"
    assert "gl" not in p
    assert "hl" not in p
    assert "pages" not in p

def test_trends_autocomplete_parse_maps_suggestions():
    sug = [{"value": "coffee maker", "type": "query"}]
    response = {"search_metadata": {}, "search_parameters": {}, "search_information": {}, "suggestions": sug}
    sections, _ = gta_parse(response)
    assert sections["suggestions"] == sug

def test_trends_autocomplete_parse_strips_search_information():
    response = {"search_metadata": {}, "search_parameters": {}, "search_information": {"q": "coffee"}, "suggestions": []}
    sections, unmapped = gta_parse(response)
    assert "search_information" not in sections
    assert unmapped is None
