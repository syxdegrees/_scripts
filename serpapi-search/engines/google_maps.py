import json
from shared.db import cache_lookup, insert_row, normalize_params
from shared.api import serpapi_get
from shared.retry import with_retry

TABLE = "serpapi_google_maps_cache"

SECTION_COLS = {"search_information", "local_results", "serpapi_pagination"}
_STRIP_KEYS = {"search_metadata", "search_parameters"}


def build_params(search_phrase, country, language, location, pages, ll=None):
    # location string not supported by Maps API — use ll (GPS coords) via engine_params instead
    p = {
        "engine": "google_maps",
        "type": "search",
        "q": search_phrase,
        "gl": country,
        "hl": language,
        "pages": pages,
    }
    if ll:
        p["ll"] = ll
    return p


def _parse_response(response):
    cleaned = {k: v for k, v in response.items() if k not in _STRIP_KEYS}
    sections = {col: cleaned.pop(col, None) for col in SECTION_COLS}
    unmapped = cleaned or None
    return sections, unmapped


def run(api_key, supabase_config, search_phrase, country, language,
        location, pages, ttl_days, **engine_params):
    call_params = build_params(search_phrase, country, language, location, pages, **engine_params)

    cached = cache_lookup(supabase_config, TABLE, search_phrase, call_params, ttl_days)
    if cached:
        return {"cache_id": cached["id"], "items_fetched": 0, "items_cached": 1, "items_stored": 0}

    combined = {}
    for page_num in range(1, pages + 1):
        api_params = {k: v for k, v in call_params.items() if k != "pages"}
        api_params["start"] = (page_num - 1) * 20
        response = with_retry(lambda p=api_params: serpapi_get(api_key, p))
        if page_num == 1:
            combined = response
        elif "local_results" in response:
            combined["local_results"] = (
                combined.get("local_results", []) + response["local_results"]
            )

    sections, unmapped = _parse_response(combined)
    row = {
        "search_phrase": search_phrase,
        "params": json.loads(normalize_params(call_params)),
        **{col: json.dumps(v) if v is not None else None for col, v in sections.items()},
        "unmapped_sections": json.dumps(unmapped) if unmapped else None,
    }
    cache_id = insert_row(supabase_config, TABLE, row)
    return {"cache_id": cache_id, "items_fetched": pages, "items_cached": 0, "items_stored": 1}
