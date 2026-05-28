import json
from shared.db import cache_lookup, insert_row, normalize_params
from shared.api import serpapi_get
from shared.retry import with_retry

TABLE = "serpapi_google_ai_mode_cache"

SECTION_COLS = {"inline_images", "text_blocks", "references", "reconstructed_markdown"}
_STRIP_KEYS = {"search_metadata", "search_parameters"}


def build_params(search_phrase, country, language, location):
    p = {
        "engine": "google_ai_mode",
        "q": search_phrase,
        "gl": country,
        "hl": language,
        "continuable": False,
    }
    if location:
        p["location"] = location
    return p


def _parse_response(response):
    cleaned = {k: v for k, v in response.items() if k not in _STRIP_KEYS}
    sections = {col: cleaned.pop(col, None) for col in SECTION_COLS}
    unmapped = cleaned or None
    return sections, unmapped


def run(api_key, supabase_config, search_phrase, country, language,
        location, pages, ttl_days, **engine_params):
    # AI Mode: single call only — pages param is intentionally ignored
    call_params = build_params(search_phrase, country, language, location)

    cached = cache_lookup(supabase_config, TABLE, search_phrase, call_params, ttl_days)
    if cached:
        return {"cache_id": cached["id"], "items_fetched": 0, "items_cached": 1, "items_stored": 0}

    response = with_retry(lambda: serpapi_get(api_key, call_params))
    sections, unmapped = _parse_response(response)
    row = {
        "search_phrase": search_phrase,
        "params": normalize_params(call_params),
        **{col: json.dumps(v) if v is not None else None for col, v in sections.items()},
        "unmapped_sections": json.dumps(unmapped) if unmapped else None,
    }
    cache_id = insert_row(supabase_config, TABLE, row)
    return {"cache_id": cache_id, "items_fetched": 1, "items_cached": 0, "items_stored": 1}
