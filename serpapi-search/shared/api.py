import requests

_SERPAPI_URL = "https://serpapi.com/search"


def serpapi_get(api_key, params):
    """Make a single SerpAPI call. Raises HTTPError on non-2xx. Caller handles retry."""
    resp = requests.get(_SERPAPI_URL, params={**params, "api_key": api_key}, timeout=60)
    resp.raise_for_status()
    return resp.json()
