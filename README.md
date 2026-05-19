# _scripts

Standalone utility scripts for use with Claude Code skills.

## Scripts

| Script | Description |
|---|---|
| `local_google_maps_scraper.py` | Scrapes Google Local business results via SerpApi and writes a deduplicated CSV. Used by the `skill-local-google-maps-scraper` Claude Code skill. |

## Setup

Each script lists its own dependencies at the top of the file.

## Notes

- Never commit `.env` files — they are gitignored.
- Scripts are standalone — no shared lib or package required.
