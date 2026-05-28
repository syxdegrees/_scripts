-- serpapi_google_light_cache
CREATE TABLE IF NOT EXISTS serpapi_google_light_cache (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase       text NOT NULL,
    params              jsonb NOT NULL,
    search_information  jsonb,
    organic_results     jsonb,
    related_searches    jsonb,
    answer_box          jsonb,
    serpapi_pagination  jsonb,
    unmapped_sections   jsonb,
    fetched_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_gl_search_phrase ON serpapi_google_light_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_gl_fetched_at    ON serpapi_google_light_cache (fetched_at);

-- serpapi_google_ai_mode_cache
-- Sections from live API refresh: inline_images, text_blocks, references, reconstructed_markdown
CREATE TABLE IF NOT EXISTS serpapi_google_ai_mode_cache (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase           text NOT NULL,
    params                  jsonb NOT NULL,
    inline_images           jsonb,
    text_blocks             jsonb,
    "references"            jsonb,
    reconstructed_markdown  jsonb,
    unmapped_sections       jsonb,
    fetched_at              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_gam_search_phrase ON serpapi_google_ai_mode_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_gam_fetched_at    ON serpapi_google_ai_mode_cache (fetched_at);

-- serpapi_google_autocomplete_cache
-- Sections from live API refresh: suggestions, verbatim_relevance (search_information stripped)
CREATE TABLE IF NOT EXISTS serpapi_google_autocomplete_cache (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase       text NOT NULL,
    params              jsonb NOT NULL,
    suggestions         jsonb,
    verbatim_relevance  jsonb,
    unmapped_sections   jsonb,
    fetched_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_gac_search_phrase ON serpapi_google_autocomplete_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_gac_fetched_at    ON serpapi_google_autocomplete_cache (fetched_at);

-- serpapi_google_forums_cache
-- Sections from live API refresh: search_information, organic_results, related_searches, serpapi_pagination
CREATE TABLE IF NOT EXISTS serpapi_google_forums_cache (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase       text NOT NULL,
    params              jsonb NOT NULL,
    search_information  jsonb,
    organic_results     jsonb,
    related_searches    jsonb,
    serpapi_pagination  jsonb,
    unmapped_sections   jsonb,
    fetched_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_gf_search_phrase ON serpapi_google_forums_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_gf_fetched_at    ON serpapi_google_forums_cache (fetched_at);

-- serpapi_google_jobs_cache
CREATE TABLE IF NOT EXISTS serpapi_google_jobs_cache (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase       text NOT NULL,
    params              jsonb NOT NULL,
    jobs_results        jsonb,
    filters             jsonb,
    serpapi_pagination  jsonb,
    unmapped_sections   jsonb,
    fetched_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_gj_search_phrase ON serpapi_google_jobs_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_gj_fetched_at    ON serpapi_google_jobs_cache (fetched_at);
