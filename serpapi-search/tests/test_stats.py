import json
from shared.stats import build_stats


def test_stats_line_starts_with_STATS():
    line = build_stats("coffee", {})
    assert line.startswith("STATS: ")


def test_stats_includes_search_phrase():
    line = build_stats("coffee", {})
    data = json.loads(line[7:])
    assert data["search_phrase"] == "coffee"


def test_stats_includes_engines():
    engines = {
        "google_light": {"cache_id": "uuid-1", "table": "serpapi_google_light_cache",
                         "items_fetched": 1, "items_cached": 0, "items_stored": 1}
    }
    line = build_stats("coffee", engines)
    data = json.loads(line[7:])
    assert data["engines"]["google_light"]["cache_id"] == "uuid-1"


def test_stats_includes_run_id_when_provided():
    line = build_stats("coffee", {}, run_id="run-uuid")
    data = json.loads(line[7:])
    assert data["run_id"] == "run-uuid"


def test_stats_omits_run_id_when_not_provided():
    line = build_stats("coffee", {})
    data = json.loads(line[7:])
    assert "run_id" not in data


def test_stats_engine_error_preserved():
    engines = {"google_jobs": {"error": "timeout after 4 attempts"}}
    line = build_stats("coffee", engines)
    data = json.loads(line[7:])
    assert data["engines"]["google_jobs"]["error"] == "timeout after 4 attempts"
