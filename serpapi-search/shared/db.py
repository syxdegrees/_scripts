import json
import os
import requests
from datetime import datetime, timezone, timedelta

_ENV_PATH = r"C:\Users\jeshj\Desktop\Coding\_scripts\_shared\.env"


def load_env(path=None):
    p = path or _ENV_PATH
    if not os.path.exists(p):
        return
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def get_supabase_config():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url:
        print("ERROR: SUPABASE_URL not found in environment or .env")
        raise SystemExit(1)
    if not key:
        print("ERROR: SUPABASE_SECRET_KEY not found in environment or .env")
        raise SystemExit(1)
    return {"url": url.rstrip("/"), "key": key}


def _headers(config):
    return {
        "apikey": config["key"],
        "Authorization": f"Bearer {config['key']}",
        "Content-Type": "application/json",
    }


def _ttl_cutoff(ttl_days):
    return (datetime.now(timezone.utc) - timedelta(days=ttl_days)).isoformat()


def normalize_params(params: dict) -> str:
    return json.dumps(dict(sorted(params.items())), sort_keys=True)


def cache_lookup(config, table, search_phrase, params, ttl_days):
    params_str = normalize_params(params)
    url = f"{config['url']}/rest/v1/{table}"
    resp = requests.get(url, headers=_headers(config), params={
        "search_phrase": f"eq.{search_phrase}",
        "params": f"eq.{params_str}",
        "fetched_at": f"gt.{_ttl_cutoff(ttl_days)}",
        "order": "fetched_at.desc",
        "limit": "1",
    })
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def insert_row(config, table, row):
    url = f"{config['url']}/rest/v1/{table}"
    resp = requests.post(
        url,
        headers={**_headers(config), "Prefer": "return=representation"},
        json=row,
    )
    resp.raise_for_status()
    return resp.json()[0]["id"]
