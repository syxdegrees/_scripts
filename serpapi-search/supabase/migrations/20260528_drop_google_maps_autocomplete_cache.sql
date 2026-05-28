-- google_maps_autocomplete requires ll (GPS coords) as a required param,
-- making it impractical for general search use. Engine removed from skill.
DROP TABLE IF EXISTS serpapi_google_maps_autocomplete_cache;
