-- =============================================================================
-- SerpAPI Search Cache Tables v2 — 15 new engines
-- Written after API refresh (Task 10/11) — columns reflect live API responses
-- =============================================================================

-- google_local
CREATE TABLE IF NOT EXISTS serpapi_google_local_cache (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase       TEXT NOT NULL,
    params              JSONB NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    local_map           JSONB,
    local_results       JSONB,
    serpapi_pagination  JSONB,
    unmapped_sections   JSONB
);
CREATE INDEX IF NOT EXISTS idx_google_local_phrase  ON serpapi_google_local_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_google_local_fetched ON serpapi_google_local_cache (fetched_at);

-- google_maps
CREATE TABLE IF NOT EXISTS serpapi_google_maps_cache (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase       TEXT NOT NULL,
    params              JSONB NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_information  JSONB,
    local_results       JSONB,
    serpapi_pagination  JSONB,
    unmapped_sections   JSONB
);
CREATE INDEX IF NOT EXISTS idx_google_maps_phrase  ON serpapi_google_maps_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_google_maps_fetched ON serpapi_google_maps_cache (fetched_at);

-- google_maps_autocomplete
CREATE TABLE IF NOT EXISTS serpapi_google_maps_autocomplete_cache (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase       TEXT NOT NULL,
    params              JSONB NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    suggestions         JSONB,
    unmapped_sections   JSONB
);
CREATE INDEX IF NOT EXISTS idx_google_maps_ac_phrase  ON serpapi_google_maps_autocomplete_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_google_maps_ac_fetched ON serpapi_google_maps_autocomplete_cache (fetched_at);

-- google_news_light
CREATE TABLE IF NOT EXISTS serpapi_google_news_light_cache (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase       TEXT NOT NULL,
    params              JSONB NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_information  JSONB,
    news_results        JSONB,
    serpapi_pagination  JSONB,
    unmapped_sections   JSONB
);
CREATE INDEX IF NOT EXISTS idx_google_news_phrase  ON serpapi_google_news_light_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_google_news_fetched ON serpapi_google_news_light_cache (fetched_at);

-- google_patents
CREATE TABLE IF NOT EXISTS serpapi_google_patents_cache (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase       TEXT NOT NULL,
    params              JSONB NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_information  JSONB,
    organic_results     JSONB,
    summary             JSONB,
    pagination          JSONB,
    serpapi_pagination  JSONB,
    unmapped_sections   JSONB
);
CREATE INDEX IF NOT EXISTS idx_google_patents_phrase  ON serpapi_google_patents_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_google_patents_fetched ON serpapi_google_patents_cache (fetched_at);

-- google_play
CREATE TABLE IF NOT EXISTS serpapi_google_play_cache (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase       TEXT NOT NULL,
    params              JSONB NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    organic_results     JSONB,
    serpapi_pagination  JSONB,
    unmapped_sections   JSONB
);
CREATE INDEX IF NOT EXISTS idx_google_play_phrase  ON serpapi_google_play_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_google_play_fetched ON serpapi_google_play_cache (fetched_at);

-- google_play_games
CREATE TABLE IF NOT EXISTS serpapi_google_play_games_cache (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase       TEXT NOT NULL,
    params              JSONB NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    organic_results     JSONB,
    serpapi_pagination  JSONB,
    unmapped_sections   JSONB
);
CREATE INDEX IF NOT EXISTS idx_google_play_games_phrase  ON serpapi_google_play_games_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_google_play_games_fetched ON serpapi_google_play_games_cache (fetched_at);

-- google_play_movies
CREATE TABLE IF NOT EXISTS serpapi_google_play_movies_cache (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase       TEXT NOT NULL,
    params              JSONB NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    organic_results     JSONB,
    serpapi_pagination  JSONB,
    unmapped_sections   JSONB
);
CREATE INDEX IF NOT EXISTS idx_google_play_movies_phrase  ON serpapi_google_play_movies_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_google_play_movies_fetched ON serpapi_google_play_movies_cache (fetched_at);

-- google_play_books
CREATE TABLE IF NOT EXISTS serpapi_google_play_books_cache (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase       TEXT NOT NULL,
    params              JSONB NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    organic_results     JSONB,
    serpapi_pagination  JSONB,
    unmapped_sections   JSONB
);
CREATE INDEX IF NOT EXISTS idx_google_play_books_phrase  ON serpapi_google_play_books_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_google_play_books_fetched ON serpapi_google_play_books_cache (fetched_at);

-- google_scholar
CREATE TABLE IF NOT EXISTS serpapi_google_scholar_cache (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase       TEXT NOT NULL,
    params              JSONB NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_information  JSONB,
    organic_results     JSONB,
    related_searches    JSONB,
    pagination          JSONB,
    serpapi_pagination  JSONB,
    unmapped_sections   JSONB
);
CREATE INDEX IF NOT EXISTS idx_google_scholar_phrase  ON serpapi_google_scholar_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_google_scholar_fetched ON serpapi_google_scholar_cache (fetched_at);

-- google_shopping_light
CREATE TABLE IF NOT EXISTS serpapi_google_shopping_light_cache (
    id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase                TEXT NOT NULL,
    params                       JSONB NOT NULL,
    fetched_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_information           JSONB,
    shopping_results             JSONB,
    categorized_shopping_results JSONB,
    filters                      JSONB,
    serpapi_pagination           JSONB,
    unmapped_sections            JSONB
);
CREATE INDEX IF NOT EXISTS idx_google_shopping_phrase  ON serpapi_google_shopping_light_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_google_shopping_fetched ON serpapi_google_shopping_light_cache (fetched_at);

-- google_short_videos
CREATE TABLE IF NOT EXISTS serpapi_google_short_videos_cache (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase           TEXT NOT NULL,
    params                  JSONB NOT NULL,
    fetched_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_information      JSONB,
    short_video_results     JSONB,
    serpapi_pagination      JSONB,
    people_also_search_for  JSONB,
    unmapped_sections       JSONB
);
CREATE INDEX IF NOT EXISTS idx_google_short_videos_phrase  ON serpapi_google_short_videos_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_google_short_videos_fetched ON serpapi_google_short_videos_cache (fetched_at);

-- google_trends
CREATE TABLE IF NOT EXISTS serpapi_google_trends_cache (
    id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase                TEXT NOT NULL,
    params                       JSONB NOT NULL,
    fetched_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    interest_over_time           JSONB,
    compared_breakdown_by_region JSONB,
    interest_by_region           JSONB,
    related_topics               JSONB,
    related_queries              JSONB,
    unmapped_sections            JSONB
);
CREATE INDEX IF NOT EXISTS idx_google_trends_phrase  ON serpapi_google_trends_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_google_trends_fetched ON serpapi_google_trends_cache (fetched_at);

-- google_trends_autocomplete
CREATE TABLE IF NOT EXISTS serpapi_google_trends_autocomplete_cache (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase       TEXT NOT NULL,
    params              JSONB NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    suggestions         JSONB,
    unmapped_sections   JSONB
);
CREATE INDEX IF NOT EXISTS idx_google_trends_ac_phrase  ON serpapi_google_trends_autocomplete_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_google_trends_ac_fetched ON serpapi_google_trends_autocomplete_cache (fetched_at);

-- google_videos_light
CREATE TABLE IF NOT EXISTS serpapi_google_videos_light_cache (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_phrase       TEXT NOT NULL,
    params              JSONB NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_information  JSONB,
    video_results       JSONB,
    filters             JSONB,
    related_searches    JSONB,
    serpapi_pagination  JSONB,
    unmapped_sections   JSONB
);
CREATE INDEX IF NOT EXISTS idx_google_videos_phrase  ON serpapi_google_videos_light_cache (search_phrase);
CREATE INDEX IF NOT EXISTS idx_google_videos_fetched ON serpapi_google_videos_light_cache (fetched_at);
