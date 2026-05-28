import json


def build_stats(search_phrase: str, engines_results: dict, run_id: str = None) -> str:
    output = {"search_phrase": search_phrase, "engines": engines_results}
    if run_id:
        output["run_id"] = run_id
    return f"STATS: {json.dumps(output)}"
