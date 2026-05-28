#!/usr/bin/env python3
"""Unified SerpAPI search fetcher. Runs one or more engine searches, caches in Supabase, outputs STATS."""
import argparse
import json
import os
import sys

from shared.db import load_env, get_supabase_config
from shared.stats import build_stats
import engines.google_light as google_light
import engines.google_ai_mode as google_ai_mode
import engines.google_autocomplete as google_autocomplete
import engines.google_forums as google_forums
import engines.google_jobs as google_jobs
import engines.google_local as google_local
import engines.google_maps as google_maps
import engines.google_maps_autocomplete as google_maps_autocomplete
import engines.google_news_light as google_news_light
import engines.google_patents as google_patents
import engines.google_play as google_play
import engines.google_play_games as google_play_games
import engines.google_play_movies as google_play_movies
import engines.google_play_books as google_play_books
import engines.google_scholar as google_scholar
import engines.google_shopping_light as google_shopping_light
import engines.google_short_videos as google_short_videos
import engines.google_trends as google_trends
import engines.google_trends_autocomplete as google_trends_autocomplete
import engines.google_videos_light as google_videos_light

_ENGINE_MAP = {
    "google_light":               google_light,
    "google_ai_mode":             google_ai_mode,
    "google_autocomplete":        google_autocomplete,
    "google_forums":              google_forums,
    "google_jobs":                google_jobs,
    "google_local":               google_local,
    "google_maps":                google_maps,
    "google_maps_autocomplete":   google_maps_autocomplete,
    "google_news_light":          google_news_light,
    "google_patents":             google_patents,
    "google_play":                google_play,
    "google_play_games":          google_play_games,
    "google_play_movies":         google_play_movies,
    "google_play_books":          google_play_books,
    "google_scholar":             google_scholar,
    "google_shopping_light":      google_shopping_light,
    "google_short_videos":        google_short_videos,
    "google_trends":              google_trends,
    "google_trends_autocomplete": google_trends_autocomplete,
    "google_videos_light":        google_videos_light,
}

_TABLE_MAP = {
    "google_light":               "serpapi_google_light_cache",
    "google_ai_mode":             "serpapi_google_ai_mode_cache",
    "google_autocomplete":        "serpapi_google_autocomplete_cache",
    "google_forums":              "serpapi_google_forums_cache",
    "google_jobs":                "serpapi_google_jobs_cache",
    "google_local":               "serpapi_google_local_cache",
    "google_maps":                "serpapi_google_maps_cache",
    "google_maps_autocomplete":   "serpapi_google_maps_autocomplete_cache",
    "google_news_light":          "serpapi_google_news_light_cache",
    "google_patents":             "serpapi_google_patents_cache",
    "google_play":                "serpapi_google_play_cache",
    "google_play_games":          "serpapi_google_play_games_cache",
    "google_play_movies":         "serpapi_google_play_movies_cache",
    "google_play_books":          "serpapi_google_play_books_cache",
    "google_scholar":             "serpapi_google_scholar_cache",
    "google_shopping_light":      "serpapi_google_shopping_light_cache",
    "google_short_videos":        "serpapi_google_short_videos_cache",
    "google_trends":              "serpapi_google_trends_cache",
    "google_trends_autocomplete": "serpapi_google_trends_autocomplete_cache",
    "google_videos_light":        "serpapi_google_videos_light_cache",
}


def main():
    parser = argparse.ArgumentParser(description="Unified SerpAPI search fetcher")
    parser.add_argument("--search_phrase", required=True)
    parser.add_argument("--engines", nargs="+", required=True,
                        choices=list(_ENGINE_MAP.keys()))
    parser.add_argument("--country", default="us")
    parser.add_argument("--language", default="en")
    parser.add_argument("--location", default=None)
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--ttl_days", type=int, default=30)
    parser.add_argument("--run_id", default=None)
    parser.add_argument("--engine_params", default=None,
                        help="JSON string of per-engine param overrides")
    args = parser.parse_args()

    load_env()

    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        print("ERROR: SERPAPI_API_KEY not found in environment or .env")
        sys.exit(1)

    supabase_config = get_supabase_config()

    engine_params = {}
    if args.engine_params:
        try:
            engine_params = json.loads(args.engine_params)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid --engine_params JSON: {e}")
            sys.exit(1)

    results = {}
    for engine_name in args.engines:
        module = _ENGINE_MAP[engine_name]
        per_engine = engine_params.get(engine_name, {})
        try:
            result = module.run(
                api_key=api_key,
                supabase_config=supabase_config,
                search_phrase=args.search_phrase,
                country=args.country,
                language=args.language,
                location=args.location,
                pages=args.pages,
                ttl_days=args.ttl_days,
                **per_engine,
            )
            result["table"] = _TABLE_MAP[engine_name]
            results[engine_name] = result
            status = "cached" if result["items_cached"] else "stored"
            print(json.dumps({"engine": engine_name, "status": status,
                              "cache_id": result["cache_id"]}))
        except SystemExit:
            raise
        except Exception as e:
            msg = str(e)
            results[engine_name] = {"error": msg}
            print(json.dumps({"engine": engine_name, "error": msg}))

    print(build_stats(args.search_phrase, results, args.run_id))


if __name__ == "__main__":
    main()
